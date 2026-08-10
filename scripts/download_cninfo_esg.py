#!/usr/bin/env python3
import argparse
import csv
import hashlib
import html
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://www.cninfo.com.cn/new/fulltextSearch/full"
REFERER = "https://www.cninfo.com.cn/new/fulltextSearch?notautosubmit=&keyWord=ESG%E6%8A%A5%E5%91%8A"
STATIC_BASE = "https://static.cninfo.com.cn/"


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"</?em>", "", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_part(value, max_len=80):
    value = clean_text(value)
    value = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", value)
    value = re.sub(r"\s+", "", value)
    value = value.strip("._ ")
    return value[:max_len] or "unknown"


def original_pdf_filename(adjunct_url):
    name = adjunct_url.rsplit("/", 1)[-1]
    return html.unescape(name)


def report_year(title, publish_date):
    years = re.findall(r"(20\d{2})", title)
    if years:
        return years[0]
    return publish_date[:4] if publish_date else ""


def report_type(title):
    title = clean_text(title)
    if "摘要" in title:
        return "ESG报告摘要"
    if "社会责任" in title and ("ESG" in title.upper() or "环境、社会" in title):
        return "ESG暨社会责任报告"
    if "可持续发展" in title and ("ESG" in title.upper() or "环境、社会" in title):
        return "可持续发展报告"
    if "社会责任" in title:
        return "社会责任报告"
    if "ESG" in title.upper() or "环境、社会" in title or "环境、社会及管治" in title:
        return "ESG报告"
    return "其他"


def fetch_json(page_num, page_size, keyword):
    params = {
        "searchkey": keyword,
        "sdate": "",
        "edate": "",
        "isfulltext": "false",
        "sortName": "pubdate",
        "sortType": "desc",
        "pageNum": str(page_num),
        "pageSize": str(page_size),
    }
    url = f"{API_URL}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": REFERER,
        },
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(url, path, retries=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")

    if path.exists() and path.stat().st_size > 0:
        return "exists", sha256_file(path), path.stat().st_size

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/pdf,*/*",
                    "Referer": REFERER,
                },
            )
            with urlopen(req, timeout=90) as resp, tmp_path.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)

            with tmp_path.open("rb") as fh:
                head = fh.read(5)
            if head != b"%PDF-":
                raise ValueError("downloaded file is not a PDF")

            tmp_path.replace(path)
            return "downloaded", sha256_file(path), path.stat().st_size
        except Exception as exc:
            last_error = exc
            if tmp_path.exists():
                tmp_path.unlink()
            time.sleep(1.5 * attempt)

    raise RuntimeError(str(last_error))


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv_rows(path, fieldnames, rows):
    """Write metadata atomically so an interrupted run cannot truncate the ledger."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(path)


def publish_date(ms):
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def source_url(item):
    params = urlencode(
        {
            "stockCode": item.get("secCode", ""),
            "announcementId": item.get("announcementId", ""),
            "orgId": item.get("orgId", ""),
            "announcementTime": item.get("announcementTime", ""),
        }
    )
    return f"https://www.cninfo.com.cn/new/disclosure/detail?{params}"


def should_skip(item, include_english):
    title = clean_text(item.get("announcementTitle"))
    if item.get("adjunctType") != "PDF":
        return "not_pdf"
    if "摘要" in title:
        return "summary"
    if "关于披露" in title or "提示性公告" in title:
        return "announcement_notice"
    if any(
        marker in title
        for marker in (
            "通知信函",
            "通知函",
            "发布通知",
            "發佈通知",
            "鉴证声明",
            "鑒證聲明",
        )
    ):
        return "publication_notice"
    if "基金" in title and ("季度报告" in title or "季度報告" in title):
        return "fund_quarterly_report"
    if not include_english and ("英文" in title or "English" in title):
        return "english"
    if "ESG" not in title.upper() and "环境、社会" not in title and "可持续" not in title:
        return "not_esg_report"
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=120)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--keyword", default="ESG报告")
    parser.add_argument("--include-english", action="store_true")
    parser.add_argument("--out-dir", default="data/raw_pdfs")
    parser.add_argument("--index", default="data/report_index.csv")
    parser.add_argument("--log", default="data/download_log.csv")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append genuinely new reports to the existing index instead of replacing it.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    index_path = Path(args.index)
    log_path = Path(args.log)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    rows = read_csv_rows(index_path) if args.resume else []
    log_rows = read_csv_rows(log_path) if args.resume else []
    seen_ids = {row.get("id", "") for row in rows + log_rows if row.get("id", "")}
    seen_paths = {Path(row["local_path"]) for row in rows if row.get("local_path")}
    seen_companies = {row.get("company", "") for row in rows if row.get("company", "")}
    if args.resume:
        seen_paths.update(out_dir.glob("*.pdf"))
    successful = 0

    for page in range(1, args.max_pages + 1):
        data = fetch_json(page, args.page_size, args.keyword)
        announcements = data.get("announcements") or []
        if not announcements:
            break

        for item in announcements:
            ann_id = str(item.get("announcementId") or "")
            if not ann_id or ann_id in seen_ids:
                continue
            seen_ids.add(ann_id)

            title = clean_text(item.get("announcementTitle"))
            company = clean_text(item.get("secName"))
            stock_code = clean_text(item.get("secCode"))
            date = publish_date(item.get("announcementTime"))
            year = report_year(title, date)
            kind = report_type(title)
            adjunct_url = item.get("adjunctUrl") or ""
            pdf_url = STATIC_BASE + adjunct_url.lstrip("/")
            filename = f"{safe_part(stock_code)}_{safe_part(company)}_{safe_part(year)}_{safe_part(kind)}.pdf"
            local_path = out_dir / filename
            if args.resume and company in seen_companies:
                log_rows.append(
                    {
                        "id": ann_id,
                        "stock_code": stock_code,
                        "company": company,
                        "title": title,
                        "status": "skipped_duplicate_company",
                        "error": "",
                    }
                )
                continue
            if local_path in seen_paths:
                log_rows.append(
                    {
                        "id": ann_id,
                        "stock_code": stock_code,
                        "company": company,
                        "title": title,
                        "status": "skipped_duplicate_normalized_filename",
                        "error": "",
                    }
                )
                continue
            seen_paths.add(local_path)

            row = {
                "id": ann_id,
                "stock_code": stock_code,
                "company": company,
                "year": year,
                "report_type": kind,
                "title": title,
                "announcement_date": date,
                "source": "cninfo",
                "source_url": source_url(item),
                "original_title": item.get("announcementTitle") or "",
                "original_adjunct_url": adjunct_url,
                "pdf_url": pdf_url,
                "original_pdf_filename": original_pdf_filename(adjunct_url),
                "normalized_filename": filename,
                "local_path": str(local_path),
                "file_sha256": "",
                "file_size_bytes": "",
                "error": "",
            }

            skip_reason = should_skip(item, args.include_english)
            if skip_reason:
                log_rows.append(
                    {
                        "id": ann_id,
                        "stock_code": stock_code,
                        "company": company,
                        "title": title,
                        "status": f"skipped_{skip_reason}",
                        "error": "",
                    }
                )
                continue

            try:
                status, digest, size = download_file(pdf_url, local_path)
                row["file_sha256"] = digest
                row["file_size_bytes"] = size
                if status == "downloaded":
                    successful += 1
                    rows.append(row)
                    seen_companies.add(company)
                log_rows.append(
                    {
                        "id": ann_id,
                        "stock_code": stock_code,
                        "company": company,
                        "title": title,
                        "status": status,
                        "error": "",
                    }
                )
                print(f"[{successful}/{args.target}] {status}: {filename}", flush=True)
            except Exception as exc:
                log_rows.append(
                    {
                        "id": ann_id,
                        "stock_code": stock_code,
                        "company": company,
                        "title": title,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                print(f"[failed] {title}: {exc}", flush=True)

            time.sleep(0.4)
            if successful >= args.target:
                break

        if successful >= args.target:
            break
        time.sleep(0.8)

    fieldnames = [
        "id",
        "stock_code",
        "company",
        "year",
        "report_type",
        "title",
        "announcement_date",
        "source",
        "source_url",
        "original_title",
        "original_adjunct_url",
        "pdf_url",
        "original_pdf_filename",
        "normalized_filename",
        "local_path",
        "file_sha256",
        "file_size_bytes",
        "error",
    ]
    write_csv_rows(index_path, fieldnames, rows)
    write_csv_rows(log_path, ["id", "stock_code", "company", "title", "status", "error"], log_rows)

    print(f"downloaded={successful}")
    print(f"index={index_path}")
    print(f"log={log_path}")
    print(f"out_dir={out_dir}")
    if successful < args.target:
        raise SystemExit(f"only downloaded {successful}, target was {args.target}")


if __name__ == "__main__":
    main()
