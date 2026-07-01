from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_PATH = PROJECT_ROOT / "outputs/system_ui/streamlit_data.json"
RESULT_REQUIRED_COLUMNS = [
    "report_id",
    "indicator_id",
    "indicator_name",
    "dimension",
    "indicator_type",
    "status",
    "value",
    "unit",
    "evidence_quote",
    "page_no",
    "block_id",
    "block_type",
    "risk_tag",
    "risk_level",
    "caution_tag",
    "suspected_issue_type",
    "risk_reason",
]
RISK_REQUIRED_COLUMNS = [
    "risk_level",
    "suspected_issue_type",
    "risk_tag",
    "caution_tag",
    "indicator_name",
    "report_id",
    "status",
    "value",
    "unit",
    "evidence_quote",
    "page_no",
    "block_id",
    "risk_reason",
]


def load_data(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).fillna("")


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    return df


def filtered_results(df: pd.DataFrame) -> pd.DataFrame:
    filters = st.columns(6)
    with filters[0]:
        dimension = st.selectbox("dimension", ["全部"] + sorted([x for x in df["dimension"].unique() if x]))
    with filters[1]:
        indicator_type = st.selectbox("indicator_type", ["全部"] + sorted([x for x in df["indicator_type"].unique() if x]))
    with filters[2]:
        status = st.selectbox("status", ["全部"] + sorted([x for x in df["status"].unique() if x]))
    with filters[3]:
        risk_tag = st.selectbox("risk_tag", ["全部"] + sorted([x for x in df["risk_tag"].unique() if x]))
    with filters[4]:
        report_query = st.text_input("report_id 包含")
    with filters[5]:
        indicator_query = st.text_input("indicator_name 包含")

    result = df
    if dimension != "全部":
        result = result[result["dimension"] == dimension]
    if indicator_type != "全部":
        result = result[result["indicator_type"] == indicator_type]
    if status != "全部":
        result = result[result["status"] == status]
    if risk_tag != "全部":
        result = result[result["risk_tag"] == risk_tag]
    if report_query:
        result = result[result["report_id"].str.contains(report_query, case=False, na=False)]
    if indicator_query:
        result = result[result["indicator_name"].str.contains(indicator_query, case=False, na=False)]
    return result


def main() -> None:
    global pd, st
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="ESG 智能提取与质量核验系统", layout="wide")
    st.title("ESG 智能提取与质量核验系统")
    st.caption("基于既有 200 份抽取结果的证据追溯、质量诊断和抽样复核辅助；不等同于人工标注评价结论。")

    if not DATA_PATH.exists():
        st.error("未找到 outputs/system_ui/streamlit_data.json。请先运行：python3 scripts/build_streamlit_data.py")
        return

    data = load_data(str(DATA_PATH))
    results_df = ensure_columns(to_df(data.get("results", [])), RESULT_REQUIRED_COLUMNS)
    risk_df = ensure_columns(to_df(data.get("risk_cases", [])), RISK_REQUIRED_COLUMNS)
    review_df = to_df(data.get("review_samples", []))
    indicators_df = ensure_columns(to_df(data.get("indicators", [])), ["indicator_id", "indicator_name"])
    summary = data.get("summary", {})

    tabs = st.tabs(["系统总览", "公司视角", "指标视角", "证据核验", "高风险样本", "新报告接入"])

    with tabs[0]:
        st.subheader("系统总览")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("报告数", summary.get("report_count", 0))
        c2.metric("指标数", summary.get("indicator_count", 0))
        c3.metric("总结果数", summary.get("total_results", 0))
        c4.metric("具体风险样本数", summary.get("concrete_risk_cases_count", summary.get("high_risk_cases_count", 0)))
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("found", summary.get("found_count", 0))
        c6.metric("missing", summary.get("missing_count", 0))
        c7.metric("error", summary.get("error_count", 0))
        c8.metric("定量 found", summary.get("quantitative_found_count", 0))
        c9, c10, c11, c12 = st.columns(4)
        value_unit_missing = int(summary.get("quantitative_value_missing_count", 0) or 0) + int(summary.get("quantitative_unit_missing_count", 0) or 0)
        c9.metric("value/unit 缺失数", value_unit_missing)
        c10.metric("证据空缺数", summary.get("evidence_empty_count", 0))
        c11.metric("后处理修复数", summary.get("postprocess_repaired_count", 0))
        c12.metric("caution 指标提醒数", summary.get("caution_tag_count", 0))
        st.write("found/missing/error 是运行结果分布，不是人工标注评价结论。")
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("E/S/G found 分布")
            st.json(summary.get("found_by_dimension", {}))
        with col_b:
            st.write("指标类型 found 分布")
            st.json(summary.get("found_by_indicator_type", {}))
        st.write("risk_level 分布")
        st.json(summary.get("risk_level_counts", {}))

    with tabs[1]:
        st.subheader("公司视角")
        report_ids = sorted(results_df["report_id"].unique())
        selected_report = st.selectbox("选择 report_id", report_ids)
        company_df = results_df[results_df["report_id"] == selected_report].copy()
        st.write(
            f"found={int((company_df['status'] == 'found').sum())}，"
            f"missing={int((company_df['status'] == 'missing').sum())}，"
            f"error={int((company_df['status'] == 'error').sum())}"
        )
        display_cols = ["indicator_name", "dimension", "indicator_type", "status", "value", "unit", "evidence_quote", "page_no", "block_id", "risk_tag", "risk_level", "caution_tag", "suspected_issue_type"]
        st.dataframe(company_df[display_cols], use_container_width=True, height=620)

    with tabs[2]:
        st.subheader("指标视角")
        indicators = indicators_df.sort_values(["indicator_name", "indicator_id"])
        label_to_id = {f"{row['indicator_name']} [{row['indicator_id']}]": row["indicator_id"] for _, row in indicators.iterrows()}
        selected_label = st.selectbox("选择 indicator_name", list(label_to_id.keys()))
        selected_id = label_to_id[selected_label]
        indicator_df = results_df[results_df["indicator_id"] == selected_id].copy()
        status_counts = indicator_df["status"].value_counts().to_dict()
        found_rate = status_counts.get("found", 0) / len(indicator_df) if len(indicator_df) else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("found", status_counts.get("found", 0))
        c2.metric("missing", status_counts.get("missing", 0))
        c3.metric("error", status_counts.get("error", 0))
        c4.metric("found 率", f"{found_rate:.2%}")
        st.write("数值样例")
        st.dataframe(indicator_df[indicator_df["status"] == "found"][["report_id", "value", "unit", "evidence_quote", "page_no", "block_id", "risk_tag", "risk_level", "caution_tag"]].head(80), use_container_width=True, height=300)
        st.write("风险样本")
        st.dataframe(indicator_df[indicator_df["risk_tag"] != "normal"][["report_id", "status", "value", "unit", "evidence_quote", "risk_tag", "risk_level", "caution_tag", "suspected_issue_type", "risk_reason"]], use_container_width=True, height=300)

    with tabs[3]:
        st.subheader("证据核验")
        filtered = filtered_results(results_df)
        st.write(f"匹配 {len(filtered)} 条")
        export_cols = ["report_id", "indicator_name", "dimension", "indicator_type", "status", "value", "unit", "evidence_quote", "page_no", "block_id", "block_type", "risk_tag", "risk_level", "caution_tag", "suspected_issue_type"]
        st.download_button("下载筛选结果 CSV", filtered[export_cols].to_csv(index=False).encode("utf-8-sig"), "evidence_filtered.csv", "text/csv")
        st.dataframe(filtered[export_cols].head(1000), use_container_width=True, height=680)

    with tabs[4]:
        st.subheader("高风险样本")
        if risk_df.empty:
            st.info("当前没有 risk_cases 记录。")
        else:
            c1, c2 = st.columns(2)
            with c1:
                level_options = ["high", "medium", "low"]
                levels = st.multiselect("risk_level", level_options, default=["high", "medium"])
            with c2:
                indicator = st.text_input("指标名包含")
            view = risk_df
            if levels:
                view = view[view["risk_level"].isin(levels)]
            issue = st.selectbox("风险类型", ["全部"] + sorted([x for x in view["suspected_issue_type"].unique() if x]))
            if issue != "全部":
                view = view[view["suspected_issue_type"] == issue]
            if indicator:
                view = view[view["indicator_name"].str.contains(indicator, case=False, na=False)]
            st.write(f"匹配 {len(view)} 条")
            cols = ["risk_level", "suspected_issue_type", "risk_tag", "caution_tag", "indicator_name", "report_id", "status", "value", "unit", "evidence_quote", "page_no", "block_id", "risk_reason"]
            st.dataframe(view[cols], use_container_width=True, height=650)
            st.download_button("下载风险样本 CSV", view.to_csv(index=False).encode("utf-8-sig"), "risk_cases_filtered.csv", "text/csv")
        st.write("抽样复核集预览")
        if not review_df.empty:
            st.dataframe(review_df.head(200), use_container_width=True, height=300)

    with tabs[5]:
        st.subheader("新报告接入")
        st.code(data.get("new_report_command", ""), language="bash")
        st.write("输出文件：")
        st.write("- extraction_results.json")
        st.write("- extraction_results.csv")
        st.write("- run_summary.json")
        st.write("- llm_errors.csv")
        st.write("- sample_review.csv")
        st.write("- error_analysis.csv")


if __name__ == "__main__":
    main()
