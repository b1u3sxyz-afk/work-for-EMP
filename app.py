# -*- coding: utf-8 -*-
import streamlit as st
from dataclasses import dataclass
from typing import Dict, Any, List
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.units import mm
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

st.set_page_config(page_title="石家庄装备制造产业园 投决会研判（定制版）", layout="wide")

# ---------------- 基本配置（可在侧边栏调整） ----------------
CONFIG = {
    "thresholds": {"investPerMu": 300.0, "taxPerMu": 25.0},
    "horizonMonths": {"land": 36, "existingNoPolicy": 24, "ownFactoryWithPolicy": 36},
}

INDUSTRIES = {"low": "低空经济", "svc": "服务类", "eqp": "装备制造类"}
PROJECT_TYPES = {
    "land": "征地项目",
    "existingNoPolicy": "购买/租赁园区或社会现房（无需政策）",
    "ownFactoryWithPolicy": "购买园区自有厂房（需政策）",
}
NEED_TYPES = {"buy": "购买厂房", "rent": "租赁厂房", "ipark": "产业港定制建设"}
CARRIERS = {"kcg": "园区自有科创谷厂房", "ipark": "产业港厂房", "social": "社会现房"}

# ---------------- 工具函数 ----------------
def nz(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0

def compute_mu(land_mu: float, building_area: float, floor_ratio: float) -> float:
    mu_by_land = land_mu if land_mu else 0.0
    mu_by_build = (building_area / (floor_ratio * 666.67)) if (building_area and floor_ratio) else 0.0
    return mu_by_land if mu_by_land > 0 else (mu_by_build if mu_by_build > 0 else 0.0)

# ---------------- 数据结构 ----------------
@dataclass
class Model:
    # 简介
    projectName: str = ""
    locate: str = ""
    projectType: str = "land"
    landMu: float = 0.0
    buildingArea: float = 0.0
    floorRatio: float = 0.0
    investTotal: float = 0.0
    investEquipment: float = 0.0
    investCivil: float = 0.0
    expectedAnnualTax: float = 0.0
    expectedOutput: float = 0.0
    expectedJobs: int = 0
    introContent: str = ""

    # 研判1：产业与主体
    industry: str = "eqp"
    companyName: str = ""
    establishedYear: str = ""
    registeredAt: str = ""
    isLuanReg: bool = True
    importBusiness: str = ""
    newBusiness: str = ""

    # 研判2：需求/业务/资质/客户/协同
    needType: str = "buy"
    carrier: str = "kcg"
    yearsStable: int = 3
    techTitles: str = ""  # 省/国家级称号
    chainMaturity: str = "成熟"
    innovation: str = "较强"
    customerStable: str = "稳定"
    marketBase: str = "扎实"
    chainSegmentFill: str = ""
    parkStrengthen: str = ""

    # 经营趋势
    revenuePrev: float = 0.0
    revenueCurr: float = 0.0
    taxPrev: float = 0.0
    taxCurr: float = 0.0
    profitPrev: float = 0.0
    profitCurr: float = 0.0
    industryTrend: str = "向好"

    # 风险项
    riskDishonest: bool = False
    riskEnv: bool = False
    riskIllegalLand: bool = False
    riskLicenseMissing: bool = False

def evaluate(m: Model) -> Dict[str, Any]:
    mu = compute_mu(m.landMu, m.buildingArea, m.floorRatio)
    fixed_assets = m.investEquipment + m.investCivil
    invest_intensity = (fixed_assets / mu) if mu > 0 else 0.0
    tax_intensity = (m.expectedAnnualTax / mu) if mu > 0 else 0.0

    veto_reasons = []
    if m.riskDishonest: veto_reasons.append("失信被执行/严重信用风险")
    if m.riskEnv: veto_reasons.append("重大环保/安监处罚未结")
    if m.riskIllegalLand: veto_reasons.append("违法违规用地")
    if m.riskLicenseMissing: veto_reasons.append("核心资质缺失且短期不可补齐")
    veto = len(veto_reasons) > 0

    thI = CONFIG["thresholds"]["investPerMu"]
    thT = CONFIG["thresholds"]["taxPerMu"]
    pass_hard = (invest_intensity >= thI) and (tax_intensity >= thT)

    # 补齐差额（用于文案）
    invest_need = max(0.0, thI * mu - fixed_assets)
    tax_need = max(0.0, thT * mu - m.expectedAnnualTax)

    # 简单评分（用于排序/参考，不显示细则）
    score = 0
    score += min(invest_intensity / thI, 1) * 40
    score += min(tax_intensity / thT, 1) * 30
    # 企业稳定/资质/客户/协同的加分（粗略）
    if m.yearsStable >= 3: score += 10
    if "国家" in m.techTitles: score += 8
    elif "省" in m.techTitles or "河北" in m.techTitles: score += 5
    if m.customerStable == "稳定": score += 5
    if m.chainSegmentFill or m.parkStrengthen: score += 5
    score = round(min(score, 100), 1)

    # 结论与建议
    reasons: List[str] = []
    decision = "附条件通过"
    if veto:
        decision = "暂缓/拒绝"
        reasons.append("命中一票否决：" + "；".join(veto_reasons))
    else:
        if pass_hard and score >= 75:
            decision = "通过/签约"
        elif pass_hard or score >= 60:
            decision = "附条件通过"
        else:
            decision = "暂缓/拒绝"
        if not pass_hard:
            if invest_need > 0:
                reasons.append(f"投资强度未达标：需追加固定投资约 {invest_need:.0f} 万元")
            if tax_need > 0:
                reasons.append(f"税收强度未达标：需新增年税收约 {tax_need:.0f} 万元")
        # 趋势提示
        if m.revenueCurr < m.revenuePrev:
            reasons.append("近两年营收下滑，需关注订单与产能匹配")
        if m.taxCurr < m.taxPrev:
            reasons.append("近两年税收下滑，需核实产品结构与价格策略")

    # 建议清单（按你提供的五点落地）
    advice: List[str] = []
    # (1) 签约条款
    advice.append("签约：在入驻协议中明确企业注册园区、经济效益考核、厂房不可转租/分割，建立项目跟踪与服务机制，确保业务按约导入并投产达效。")
    # (2) 产业港“双同步”
    if m.needType == "ipark" or m.projectType in ["land", "ownFactoryWithPolicy"] and CARRIERS.get(m.carrier,"") == "产业港厂房":
        advice.append("产业港项目：产发公司采取“双同步”推进——推进载体建设（征收→设计→施工→验收），并同步匹配地块/厂房与企业需求，防止“签约不落地”。")
    # (3) 经济效益≥2000 万触发入统指导
    if m.expectedAnnualTax >= 2000 or (m.expectedOutput and m.expectedOutput >= 20000):
        advice.append("经济服务局做好项目经济指标跟踪与入统指导，帮助企业熟悉统计口径与申报流程，确保达条件后及时纳入统计范围。")
    # (4) 产业协同服务
    if m.chainSegmentFill or m.parkStrengthen:
        advice.append("协同发展：产发公司与经济服务局协同做好企业服务与培育，围绕补链环节开展上下游对接，增强园区相关环节实力。")
    # (5) 征地与手续服务
    if m.projectType == "land":
        advice.append("征地项目：产发公司与企业对接土地收储与摘牌，协助办理环评、消防、安评等，确保建设与生产合法合规。")

    # 简介段落（完全按你给的模板）
    intro = (
        f"{m.projectName}，计划投资{m.investTotal:.0f}万元，{m.locate or '拟选址待定'}；"
        f"占地{m.landMu or 0:.2f}亩/实际建筑面积{m.buildingArea or 0:.0f}㎡，"
        f"建设内容：{m.introContent or '——'}；预计经济效益：年税收{m.expectedAnnualTax:.0f}万元"
        + (f"、年产值{m.expectedOutput:.0f}万元" if m.expectedOutput else "")
        + (f"、就业{m.expectedJobs}人" if m.expectedJobs else "")
        + "。"
    )

    # 研判文字 1（项目类别与主体）
    reg_part = f"{m.companyName}，{m.establishedYear}年注册于{m.registeredAt or '—'}；"
    if m.isLuanReg:
        reg_part += f"拟将{m.importBusiness or '相关'}业务导入园区"
        if m.newBusiness:
            reg_part += f"，并拓展{m.newBusiness}新业务"
        reg_part += "。"
    else:
        reg_part += f"尚未注册于园区，拟将{m.importBusiness or '相关'}业务导入园区"
        if m.newBusiness:
            reg_part += f"，并拓展{m.newBusiness}新业务"
        reg_part += "。"
    judge_1 = (
        f"项目为{INDUSTRIES[m.industry]}方向，符合园区发展规划；项目主体为{reg_part}"
    )

    # 研判文字 2（需求与能力、协同）
    need_txt = f"该项目主要需求为{NEED_TYPES[m.needType]}，拟承接载体：{CARRIERS[m.carrier]}。"
    ability_txt = (
        f"项目拟开展业务：{m.introContent or '—'}；企业已稳定运行{m.yearsStable}年以上，"
        f"具有{m.techTitles or '相关'}技术/称号，产业链{m.chainMaturity}、技术创新{m.innovation}，"
        f"客户资源{m.customerStable}、市场基础{m.marketBase}。"
    )
    synergy_txt = ""
    if m.chainSegmentFill or m.parkStrengthen:
        synergy_txt = (
            f"入园后，有望填补园区产业链的“{m.chainSegmentFill or '—'}”环节，"
            f"增强园区在“{m.parkStrengthen or '—'}”环节的实力。"
        )
    judge_2 = need_txt + ability_txt + synergy_txt

    # 研判文字 3（经营与趋势）
    rev_trend = "稳中向好" if m.revenueCurr >= m.revenuePrev and m.taxCurr >= m.taxPrev else "存在波动"
    econ_txt = (
        f"企业近两年营收由{m.revenuePrev:.0f}万元增至{m.revenueCurr:.0f}万元，"
        f"税收由{m.taxPrev:.0f}万元增至{m.taxCurr:.0f}万元，整体{rev_trend}；"
        f"结合行业当前趋势“{m.industryTrend}”，预计落地园区后经济效益"
        f"{'向好' if rev_trend=='稳中向好' or m.industryTrend=='向好' else '需持续观察'}，"
        f"并带动产业协同发展。"
    )
    # 达标校验提示
    standard = f"达标校验：按折算亩{mu:.2f}亩，投资强度{invest_intensity:.1f}万/亩，税收强度{tax_intensity:.1f}万/亩·年；阈值为投资≥{thI}万/亩、税收≥{thT}万/亩·年。"

    return {
        "mu": mu,
        "investIntensity": invest_intensity,
        "taxIntensity": tax_intensity,
        "passHard": pass_hard,
        "veto": veto,
        "vetoReasons": veto_reasons,
        "investNeed": invest_need,
        "taxNeed": tax_need,
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "advice": advice,
        "intro": intro,
        "judge1": judge_1,
        "judge2": judge_2,
        "judge3": econ_txt,
        "standard": standard,
    }

# ---------------- 文档导出 ----------------
def build_docx(m: Model, ev: Dict[str, Any]) -> BytesIO:
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = '宋体'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    style.font.size = Pt(11)

    doc.add_heading('项目研判报告', level=1)
    doc.add_paragraph('（自动生成 · 仅供投决会参考）')

    doc.add_heading('一、项目简介', level=2)
    doc.add_paragraph(ev["intro"])

    doc.add_heading('二、研判', level=2)
    doc.add_paragraph("1）项目类别与主体")
    doc.add_paragraph(ev["judge1"])
    doc.add_paragraph("2）需求与能力、产业协同")
    doc.add_paragraph(ev["judge2"])
    doc.add_paragraph("3）经营情况与趋势")
    doc.add_paragraph(ev["judge3"])
    doc.add_paragraph(ev["standard"])
    if not ev["passHard"]:
        if ev["investNeed"] > 0:
            doc.add_paragraph(f"— 投资补齐建议：追加固定投资约 {ev['investNeed']:.0f} 万元。")
        if ev["taxNeed"] > 0:
            doc.add_paragraph(f"— 税收补齐建议：新增年税收约 {ev['taxNeed']:.0f} 万元。")
    if ev["veto"]:
        doc.add_paragraph("— 风险提示（命中一票否决）："+ "；".join(ev["vetoReasons"]))

    doc.add_heading('三、结论与建议', level=2)
    doc.add_paragraph(f"结论：{ev['decision']}")
    if ev["reasons"]:
        doc.add_paragraph("主要原因：")
        for r in ev["reasons"]:
            doc.add_paragraph(r, style=None).style = doc.styles['List Bullet']
    doc.add_paragraph("建议：")
    for a in ev["advice"]:
        doc.add_paragraph(a, style=None).style = doc.styles['List Bullet']

    bio = BytesIO(); doc.save(bio); bio.seek(0); return bio

def build_pdf(m: Model, ev: Dict[str, Any]) -> BytesIO:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    W, H = A4
    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    c.setTitle("项目研判报告")

    def draw_text(x, y, text, size=11):
        c.setFont('STSong-Light', size)
        line_height = size * 1.32
        max_chars = 38
        for para in text.split("\\n"):
            while len(para) > max_chars:
                c.drawString(x, y, para[:max_chars]); y -= line_height
                para = para[max_chars:]
            c.drawString(x, y, para); y -= line_height
        return y - 4

    margin = 20*mm; y = H - margin
    c.setFont('STSong-Light', 16); c.drawString(margin, y, "项目研判报告"); y -= 10*mm
    c.setFont('STSong-Light', 10); c.drawString(margin, y, "（自动生成 · 仅供投决会参考）"); y -= 8*mm

    c.setFont('STSong-Light', 13); c.drawString(margin, y, "一、项目简介"); y -= 7*mm
    y = draw_text(margin, y, ev["intro"])

    c.setFont('STSong-Light', 13); c.drawString(margin, y, "二、研判"); y -= 7*mm
    y = draw_text(margin, y, "1）项目类别与主体")
    y = draw_text(margin, y, ev["judge1"])
    y = draw_text(margin, y, "2）需求与能力、产业协同")
    y = draw_text(margin, y, ev["judge2"])
    y = draw_text(margin, y, "3）经营情况与趋势")
    y = draw_text(margin, y, ev["judge3"])
    y = draw_text(margin, y, ev["standard"])
    if not ev["passHard"]:
        if ev["investNeed"] > 0:
            y = draw_text(margin, y, f"— 投资补齐建议：追加固定投资约 {ev['investNeed']:.0f} 万元。")
        if ev["taxNeed"] > 0:
            y = draw_text(margin, y, f"— 税收补齐建议：新增年税收约 {ev['taxNeed']:.0f} 万元。")
    if ev["veto"]:
        y = draw_text(margin, y, "— 风险提示（命中一票否决）："+ "；".join(ev["vetoReasons"]))

    c.setFont('STSong-Light', 13); c.drawString(margin, y, "三、结论与建议"); y -= 7*mm
    y = draw_text(margin, y, f"结论：{ev['decision']}")
    if ev["reasons"]:
        y = draw_text(margin, y, "主要原因：")
        for r in ev["reasons"]:
            y = draw_text(margin+8, y, f"• {r}")
    y = draw_text(margin, y, "建议：")
    for a in ev["advice"]:
        y = draw_text(margin+8, y, f"• {a}")

    c.showPage(); c.save(); bio.seek(0); return bio

# ---------------- UI ----------------
st.markdown("## 石家庄装备制造产业园 — 投资决策委员会 项目研判（定制版）")
st.caption("按照你提供的报告结构与表述自动生成文字，校验“投资≥300万/亩、税收≥25万/亩”，并给出补齐差额与建议。")

with st.sidebar:
    st.subheader("参数设置")
    CONFIG["thresholds"]["investPerMu"] = float(st.number_input("固定投资阈值（万/亩）", 0.0, 10000.0, CONFIG["thresholds"]["investPerMu"]))
    CONFIG["thresholds"]["taxPerMu"] = float(st.number_input("税收强度阈值（万/亩·年）", 0.0, 1000.0, CONFIG["thresholds"]["taxPerMu"]))
    CONFIG["horizonMonths"]["land"] = st.number_input("征地达产期（月）", 6, 60, CONFIG["horizonMonths"]["land"])
    CONFIG["horizonMonths"]["existingNoPolicy"] = st.number_input("现房达产期（月）", 6, 60, CONFIG["horizonMonths"]["existingNoPolicy"])
    CONFIG["horizonMonths"]["ownFactoryWithPolicy"] = st.number_input("自有厂房达产期（月）", 6, 60, CONFIG["horizonMonths"]["ownFactoryWithPolicy"])

col1, col2 = st.columns(2)

with col1:
    st.header("一、项目简介（输入）")
    projectName = st.text_input("项目名称", value="高端装备制造项目")
    locate = st.text_input("拟选址", value="栾城区科创谷/产业港")
    projectType = st.selectbox("项目类型", options=list(PROJECT_TYPES.keys()), format_func=lambda k: PROJECT_TYPES[k])

    landMu = st.number_input("占地（亩）", min_value=0.0, step=0.01, value=0.0)
    buildingArea = st.number_input("实际建筑面积（㎡）", min_value=0.0, step=1.0, value=0.0)
    floorRatio = st.number_input("容积率（折算用）", min_value=0.0, step=0.1, value=0.0)

    investTotal = st.number_input("计划总投资（万元）", min_value=0.0, value=10000.0, step=100.0)
    investEquipment = st.number_input("设备投资（万元）", min_value=0.0, value=6000.0, step=100.0)
    investCivil = st.number_input("土建投资（万元）", min_value=0.0, value=3000.0, step=100.0)
    expectedAnnualTax = st.number_input("预计年税收（万元）", min_value=0.0, value=1500.0, step=10.0)
    expectedOutput = st.number_input("预计年产值（万元，可选）", min_value=0.0, value=0.0, step=100.0)
    expectedJobs = st.number_input("预计就业人数（人，可选）", min_value=0, value=0, step=1)
    introContent = st.text_area("建设内容（一句话）", value="新建高精度机加工产线与装配线")

with col2:
    st.header("二、研判要点（输入）")
    industry = st.selectbox("产业大类", options=list(INDUSTRIES.keys()), format_func=lambda k: INDUSTRIES[k])
    companyName = st.text_input("项目主体（公司名称）", value="某装备制造有限公司")
    establishedYear = st.text_input("注册年份", value="2016")
    registeredAt = st.text_input("注册地", value="石家庄市栾城区")
    isLuanReg = st.checkbox("若注册在栾城区，则视为“拟将业务导入园区”", value=True)
    importBusiness = st.text_input("拟导入园区的业务", value="核心零部件制造与总装")
    newBusiness = st.text_input("拓展新业务（可选）", value="")

    needType = st.selectbox("主要需求", options=list(NEED_TYPES.keys()), format_func=lambda k: NEED_TYPES[k])
    carrier = st.selectbox("载体选择", options=list(CARRIERS.keys()), format_func=lambda k: CARRIERS[k])
    yearsStable = st.number_input("企业稳定运行年限", min_value=0, value=5, step=1)
    techTitles = st.text_input("技术/称号（如省/国家级、高新、专精特新等）", value="省级专精特新、小巨人")
    chainMaturity = st.selectbox("产业链条成熟度", options=["完善","成熟","一般"])
    innovation = st.selectbox("技术创新能力", options=["强","较强","一般"])
    customerStable = st.selectbox("客户资源稳定性", options=["稳定","一般","不稳定"])
    marketBase = st.selectbox("市场基础", options=["扎实","一般","较弱"])
    chainSegmentFill = st.text_input("入园后可填补的产业链环节（可选）", value="关键零部件加工")
    parkStrengthen = st.text_input("可增强的园区环节（可选）", value="精密加工与总装")

    st.markdown("**一票否决（任一为“是”建议拒绝）**")
    riskDishonest = st.checkbox("失信被执行/严重信用风险", value=False)
    riskEnv = st.checkbox("重大环保/安监处罚未结", value=False)
    riskIllegalLand = st.checkbox("违法违规用地", value=False)
    riskLicenseMissing = st.checkbox("核心资质缺失且短期不可补齐", value=False)

    st.header("三、经营与趋势（输入）")
    revenuePrev = st.number_input("上年营收（万元）", min_value=0.0, value=20000.0, step=100.0)
    revenueCurr = st.number_input("当年营收（万元）", min_value=0.0, value=22000.0, step=100.0)
    taxPrev = st.number_input("上年税收（万元）", min_value=0.0, value=1200.0, step=10.0)
    taxCurr = st.number_input("当年税收（万元）", min_value=0.0, value=1300.0, step=10.0)
    profitPrev = st.number_input("上年净利润（万元）", min_value=-10000.0, value=1200.0, step=10.0)
    profitCurr = st.number_input("当年净利润（万元）", min_value=-10000.0, value=1300.0, step=10.0)
    industryTrend = st.selectbox("行业趋势", options=["向好","平稳","承压"])

# 组装模型
m = Model(
    projectName=projectName, locate=locate, projectType=projectType,
    landMu=landMu, buildingArea=buildingArea, floorRatio=floorRatio,
    investTotal=investTotal, investEquipment=investEquipment, investCivil=investCivil,
    expectedAnnualTax=expectedAnnualTax, expectedOutput=expectedOutput, expectedJobs=int(expectedJobs),
    introContent=introContent,
    industry=industry, companyName=companyName, establishedYear=establishedYear, registeredAt=registeredAt,
    isLuanReg=isLuanReg, importBusiness=importBusiness, newBusiness=newBusiness,
    needType=needType, carrier=carrier, yearsStable=int(yearsStable), techTitles=techTitles,
    chainMaturity=chainMaturity, innovation=innovation, customerStable=customerStable, marketBase=marketBase,
    chainSegmentFill=chainSegmentFill, parkStrengthen=parkStrengthen,
    revenuePrev=revenuePrev, revenueCurr=revenueCurr, taxPrev=taxPrev, taxCurr=taxCurr,
    profitPrev=profitPrev, profitCurr=profitCurr, industryTrend=industryTrend,
    riskDishonest=riskDishonest, riskEnv=riskEnv, riskIllegalLand=riskIllegalLand, riskLicenseMissing=riskLicenseMissing,
)

# 评估与生成报告段落
ev = evaluate(m)

# 概览卡片
st.markdown("---")
k1,k2,k3,k4 = st.columns(4)
k1.metric("折算亩", f"{compute_mu(m.landMu, m.buildingArea, m.floorRatio):.2f} 亩")
k2.metric("投资强度", f"{ev['investIntensity']:.1f} 万/亩")
k3.metric("税收强度", f"{ev['taxIntensity']:.1f} 万/亩·年")
k4.metric("参考评分", f"{ev['score']} / 100")

# 预览报告（完全按你的结构）
st.markdown("### 预览 · 研判报告")
st.markdown(f"""
**一、项目简介**  
{ev['intro']}

**二、研判**  
1）项目类别与主体  
{ev['judge1']}

2）需求与能力、产业协同  
{ev['judge2']}

3）经营情况与趋势  
{ev['judge3']}

{ev['standard']}
""")
if not ev["passHard"]:
    if ev["investNeed"] > 0:
        st.write(f"- 投资补齐建议：追加固定投资约 **{ev['investNeed']:.0f} 万元**")
    if ev["taxNeed"] > 0:
        st.write(f"- 税收补齐建议：新增年税收约 **{ev['taxNeed']:.0f} 万元**")
if ev["veto"]:
    st.error("风险提示（命中一票否决）："+ "；".join(ev["vetoReasons"]))

st.markdown(f"**三、结论与建议**  \n结论：:{"green" if ev['decision']=='通过/签约' else 'orange' if ev['decision']=='附条件通过' else 'gray'}[{ev['decision']}]")
if ev["reasons"]:
    st.write("主要原因：")
    for r in ev["reasons"]:
        st.write(f"- {r}")
st.write("建议：")
for a in ev["advice"]:
    st.write(f"- {a}")

# 导出
docx_bytes = build_docx(m, ev)
pdf_bytes = build_pdf(m, ev)
c1, c2 = st.columns(2)
c1.download_button("导出 Word（DOCX）", data=docx_bytes, file_name=f"{m.projectName or '项目'}_研判报告_定制版.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
c2.download_button("导出 PDF", data=pdf_bytes, file_name=f"{m.projectName or '项目'}_研判报告_定制版.pdf", mime="application/pdf")

st.caption("口径提示：固定投资强度=（设备+土建）/折算亩；税收强度=年税收/折算亩。三类项目统一口径；产业港项目注意“双同步”推进。")
