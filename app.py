# -*- coding: utf-8 -*-
import streamlit as st
from io import BytesIO
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.units import mm
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

st.set_page_config(page_title="园区招商项目研判 · Streamlit", layout="wide")

# ---------- 配置 ----------
CONFIG = {
    "thresholds": {"investPerMu": 300.0, "taxPerMu": 25.0},
    "horizonMonths": {"land": 36, "existingNoPolicy": 24, "ownFactoryWithPolicy": 36},
    "weights": {
        "hard": {"invest": 20, "tax": 15, "funds": 5},
        "strength": {"trend": 10, "customers": 8, "certs": 7, "finance": 5},
        "synergy": {"chain": 10, "match": 6, "spillover": 4},
        "feasibility": {"carrier": 5, "approvals": 4, "resources": 1},
    },
}

INDUSTRIES = {
    "low_altitude": "低空经济",
    "equipment": "装备制造",
    "services": "服务配套",
}

PROJECT_TYPES = {
    "land": "征地项目",
    "existingNoPolicy": "购/租现房（无需政策）",
    "ownFactoryWithPolicy": "购园区自有厂房（需政策）",
}

# ---------- 工具函数 ----------
def number_or_zero(v) -> float:
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

def clamp(v: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, v))

def trend_score(prev: float, curr: float) -> float:
    if curr > prev * 1.05:
        return 1.0
    if curr >= prev * 0.95:
        return 0.6
    return 0.2

def ratio_band_score(ratio: float, bands=(0.5, 0.7, 0.9)) -> float:
    # ratio越小越好，这里用于简化财务健康度（净利为负 → 风险高）
    if ratio <= bands[0]:
        return 1.0
    if ratio <= bands[1]:
        return 0.7
    if ratio <= bands[2]:
        return 0.4
    return 0.2

# ---------- 数据结构 ----------
@dataclass
class ModelInput:
    projectName: str = ""
    industry: str = "equipment"
    projectType: str = "land"
    locationNote: str = ""
    landMu: float = 0.0
    buildingArea: float = 0.0
    floorRatio: float = 0.0
    investTotal: float = 0.0
    investEquipment: float = 0.0
    investCivil: float = 0.0
    expectedAnnualTax: float = 0.0
    companyName: str = ""
    establishedYear: str = ""
    registeredInLuan: bool = True
    revenuePrev: float = 0.0
    revenueCurr: float = 0.0
    taxPrev: float = 0.0
    taxCurr: float = 0.0
    netProfitPrev: float = 0.0
    netProfitCurr: float = 0.0
    ordersInHand: float = 0.0
    bankCreditReady: bool = False
    topCustomersStable: bool = False
    certHighTech: bool = False
    certSpecTiny: bool = False
    certOtherCount: int = 0
    riskDishonest: bool = False
    riskEnvSafety: bool = False
    riskIllegalLand: bool = False
    riskCoreLicenseMissing: bool = False
    synergyLevel: int = 1   # 0/1/2
    approvalsLevel: int = 1 # 0/1/2
    carrierMatch: int = 1   # 0/1/2
    resourcesLevel: int = 1 # 0/1/2
    customIntro: str = ""
    policyCoverYearsLimit: float = 5.0  # 需政策类型的覆盖期阈值（年），仅文案展示

def evaluate(m: ModelInput) -> Dict[str, Any]:
    mu = compute_mu(m.landMu, m.buildingArea, m.floorRatio)
    fixed_assets = m.investEquipment + m.investCivil
    invest_intensity = (fixed_assets / mu) if mu > 0 else 0.0
    tax_intensity = (m.expectedAnnualTax / mu) if mu > 0 else 0.0

    veto_reasons: List[str] = []
    if m.riskDishonest: veto_reasons.append("失信被执行/严重信用风险")
    if m.riskEnvSafety: veto_reasons.append("重大环保/安监处罚未结")
    if m.riskIllegalLand: veto_reasons.append("违法违规用地")
    if m.riskCoreLicenseMissing: veto_reasons.append("核心资质缺失且短期不可补齐")
    veto = len(veto_reasons) > 0

    W = CONFIG["weights"]
    T = CONFIG["thresholds"]

    # A 硬达标性 0-40
    aInvest = clamp(invest_intensity / T["investPerMu"], 0, 1) * W["hard"]["invest"]
    aTax = clamp(tax_intensity / T["taxPerMu"], 0, 1) * W["hard"]["tax"]
    aFunds = (W["hard"]["funds"] if m.bankCreditReady else 0)
    A = aInvest + aTax + aFunds

    # B 企业实力 0-30
    revScore = trend_score(m.revenuePrev, m.revenueCurr)
    taxScore = trend_score(m.taxPrev, m.taxCurr)
    trendPoints = (revScore * 0.6 + taxScore * 0.4) * W["strength"]["trend"]
    custPoints = (W["strength"]["customers"] if m.topCustomersStable else 0)
    cert_count = (1 if m.certHighTech else 0) + (1 if m.certSpecTiny else 0) + max(0, int(m.certOtherCount))
    cert_factor = 1 if cert_count >= 3 else (0.8 if cert_count == 2 else (0.6 if cert_count == 1 else 0.3))
    certPoints = cert_factor * W["strength"]["certs"]
    # 简化财务健康：净利为正→0.6；净利为负→0.9（越大越差，故得分越低）
    finance_ratio = 0.6 if m.netProfitCurr >= 0 else 0.9
    financePoints = ratio_band_score(finance_ratio, (0.5, 0.7, 0.9)) * W["strength"]["finance"]
    B = trendPoints + custPoints + certPoints + financePoints

    # C 产业协同 0-20
    chainPoints = (1 if m.synergyLevel == 2 else 0.6 if m.synergyLevel == 1 else 0.3) * W["synergy"]["chain"]
    matchPoints = 1.0 * W["synergy"]["match"]  # 产业枚举即认为匹配
    spillPoints = (1 if m.registeredInLuan else 0.6) * W["synergy"]["spillover"]
    C = chainPoints + matchPoints + spillPoints

    # D 可落地与合规 0-10
    carrierPoints = (1 if m.carrierMatch == 2 else 0.6 if m.carrierMatch == 1 else 0.2) * W["feasibility"]["carrier"]
    approvalsPoints = (1 if m.approvalsLevel == 2 else 0.6 if m.approvalsLevel == 1 else 0.2) * W["feasibility"]["approvals"]
    resourcesPoints = (1 if m.resourcesLevel == 2 else 0.6 if m.resourcesLevel == 1 else 0.2) * W["feasibility"]["resources"]
    D = carrierPoints + approvalsPoints + resourcesPoints

    total = round(A + B + C + D, 1)

    pass_hard = (invest_intensity >= T["investPerMu"]) and (tax_intensity >= T["taxPerMu"])

    # 决策建议
    decision = "附条件通过"
    reasons: List[str] = []
    if veto:
        decision = "暂缓/拒绝"
        reasons.append("命中一票否决：" + "；".join(veto_reasons))
    elif not pass_hard:
        if total >= 70:
            decision = "附条件通过"
            if invest_intensity < T["investPerMu"]:
                reasons.append("投资强度低于300万/亩，需增资或优化产线")
            if tax_intensity < T["taxPerMu"]:
                reasons.append("税收强度低于25万/亩，需补充订单/调整产品结构")
        else:
            decision = "暂缓/拒绝"
            reasons.append("硬指标未达标且综合评分偏低")
    else:
        if total >= 80:
            decision = "通过/签约"
        elif total >= 60:
            decision = "附条件通过"
            reasons.append("建议补齐要件后签约，提高成功率")
        else:
            decision = "暂缓/拒绝"
            reasons.append("综合评分不足")

    clauses: List[str] = []
    if decision != "暂缓/拒绝":
        clauses.extend([
            "注册地：石家庄市栾城区",
            "经济效益考核：投资/税收强度达标（合同约定）",
            "厂房不可转租或分割",
            "业务导入清单与时间表（签约即生效）",
        ])
    if m.projectType == "ownFactoryWithPolicy" and decision != "暂缓/拒绝":
        clauses.append("政策支持：按净新增税收覆盖期≤X年分期兑现；未达标触发追偿/递延")

    horizon = CONFIG["horizonMonths"][m.projectType]

    auto_intro = f"""{m.projectName or '某项目'}，计划投资{m.investTotal:.0f}万元，{m.locationNote or '拟选址待定'}；\\
占地{m.landMu or '-'}亩/建筑面积{m.buildingArea or '-'}㎡，建设内容：{m.customIntro or '——'}；\\
预计达产后年税收{m.expectedAnnualTax:.0f}万元，按{horizon}个月达产测算。"""

    return {
        "mu": mu,
        "fixedAssets": fixed_assets,
        "investIntensity": invest_intensity,
        "taxIntensity": tax_intensity,
        "veto": veto,
        "vetoReasons": veto_reasons,
        "sectionScores": {"A": round(A,1), "B": round(B,1), "C": round(C,1), "D": round(D,1)},
        "total": total,
        "passHard": pass_hard,
        "decision": decision,
        "reasons": reasons,
        "clauses": clauses,
        "autoIntro": auto_intro,
        "horizon": horizon,
    }

# ---------- 导出：DOCX ----------
def build_docx_report(m: ModelInput, ev: dict) -> BytesIO:
    doc = Document()
    # 设置中文字体
    style = doc.styles['Normal']
    style.font.name = '宋体'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    style.font.size = Pt(11)

    title = doc.add_heading('项目研判报告', level=1)
    title.alignment = 0

    doc.add_paragraph('（自动生成 · 仅供投决会参考）')

    # 一、项目简介
    doc.add_heading('一、项目简介', level=2)
    doc.add_paragraph(ev["autoIntro"])
    p = doc.add_paragraph()
    p.add_run(f"项目类型：{PROJECT_TYPES.get(m.projectType,'')}；产业类别：{INDUSTRIES.get(m.industry,'')}")
    p = doc.add_paragraph()
    p.add_run(f"折算亩：{ev['mu']:.2f} 亩；投资强度：{ev['investIntensity']:.1f} 万/亩；税收强度：{ev['taxIntensity']:.1f} 万/亩·年")
    p = doc.add_paragraph()
    p.add_run(f"达产期参考：{ev['horizon']} 个月")

    # 二、阈值校验与评分
    doc.add_heading('二、阈值校验与评分', level=2)
    doc.add_paragraph(f"硬指标阈值：投资≥{CONFIG['thresholds']['investPerMu']} 万/亩，税收≥{CONFIG['thresholds']['taxPerMu']} 万/亩·年")
    doc.add_paragraph("一票否决：" + ("命中（" + "，".join(ev["vetoReasons"]) + "）" if ev["veto"] else "未命中"))
    doc.add_paragraph(f"A 硬达标性：{ev['sectionScores']['A']} / 40")
    doc.add_paragraph(f"B 企业实力：{ev['sectionScores']['B']} / 30")
    doc.add_paragraph(f"C 产业协同：{ev['sectionScores']['C']} / 20")
    doc.add_paragraph(f"D 可落地与合规：{ev['sectionScores']['D']} / 10")
    doc.add_paragraph(f"综合评分：{ev['total']} / 100")

    # 三、研判结论与建议
    doc.add_heading('三、研判结论与建议', level=2)
    doc.add_paragraph(f"结论：{ev['decision']}")
    if ev["reasons"]:
        doc.add_paragraph("主要原因：")
        for r in ev["reasons"]:
            doc.add_paragraph(r, style=None).style = doc.styles['List Bullet']
    if ev["clauses"]:
        doc.add_paragraph("签约/附条件条款建议：")
        for c in ev["clauses"]:
            doc.add_paragraph(c, style=None).style = doc.styles['List Bullet']

    # 四、补充说明
    doc.add_heading('四、补充说明', level=2)
    doc.add_paragraph("若为“购园区自有厂房（需政策）”类型，需在投决前完成净新增税收覆盖期测算，并明确分期兑现与追偿/递延机制。")

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# ---------- 导出：PDF ----------
def build_pdf_report(m: ModelInput, ev: dict) -> BytesIO:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    W, H = A4
    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    c.setTitle("项目研判报告")

    def draw_text(x, y, text, font='STSong-Light', size=11):
        c.setFont(font, size)
        # 简单换行：按行分割
        line_height = size * 1.35
        max_chars = 38  # 粗略估计（中文等宽）
        lines = []
        for para in text.split("\\n"):
            while len(para) > max_chars:
                lines.append(para[:max_chars])
                para = para[max_chars:]
            lines.append(para)
        for i, ln in enumerate(lines):
            c.drawString(x, y - i * line_height, ln)
        return y - len(lines) * line_height - 4

    margin = 20 * mm
    y = H - margin
    c.setFont('STSong-Light', 16)
    c.drawString(margin, y, "项目研判报告")
    y -= 10 * mm
    c.setFont('STSong-Light', 10)
    c.drawString(margin, y, "（自动生成 · 仅供投决会参考）")
    y -= 8 * mm

    # 一、项目简介
    c.setFont('STSong-Light', 13); c.drawString(margin, y, "一、项目简介"); y -= 7 * mm
    intro_lines = [
        ev["autoIntro"],
        f"项目类型：{PROJECT_TYPES.get(m.projectType,'')}；产业类别：{INDUSTRIES.get(m.industry,'')}",
        f"折算亩：{ev['mu']:.2f} 亩；投资强度：{ev['investIntensity']:.1f} 万/亩；税收强度：{ev['taxIntensity']:.1f} 万/亩·年",
        f"达产期参考：{ev['horizon']} 个月",
    ]
    for t in intro_lines:
        y = draw_text(margin, y, t, size=11)

    # 二、阈值校验与评分
    c.setFont('STSong-Light', 13); c.drawString(margin, y, "二、阈值校验与评分"); y -= 7 * mm
    y = draw_text(margin, y, f"硬指标阈值：投资≥{CONFIG['thresholds']['investPerMu']} 万/亩，税收≥{CONFIG['thresholds']['taxPerMu']} 万/亩·年")
    veto_text = "一票否决：" + ("命中（" + "，".join(ev["vetoReasons"]) + "）" if ev["veto"] else "未命中")
    y = draw_text(margin, y, veto_text)
    y = draw_text(margin, y, f"A 硬达标性：{ev['sectionScores']['A']} / 40")
    y = draw_text(margin, y, f"B 企业实力：{ev['sectionScores']['B']} / 30")
    y = draw_text(margin, y, f"C 产业协同：{ev['sectionScores']['C']} / 20")
    y = draw_text(margin, y, f"D 可落地与合规：{ev['sectionScores']['D']} / 10")
    y = draw_text(margin, y, f"综合评分：{ev['total']} / 100")

    # 三、研判结论与建议
    c.setFont('STSong-Light', 13); c.drawString(margin, y, "三、研判结论与建议"); y -= 7 * mm
    y = draw_text(margin, y, f"结论：{ev['decision']}")
    if ev["reasons"]:
        y = draw_text(margin, y, "主要原因：")
        for r in ev["reasons"]:
            y = draw_text(margin + 8, y, f"• {r}")
    if ev["clauses"]:
        y = draw_text(margin, y, "签约/附条件条款建议：")
        for ctext in ev["clauses"]:
            y = draw_text(margin + 8, y, f"• {ctext}")

    # 四、补充说明
    c.setFont('STSong-Light', 13); c.drawString(margin, y, "四、补充说明"); y -= 7 * mm
    y = draw_text(margin, y, "若为“购园区自有厂房（需政策）”类型，需在投决前完成净新增税收覆盖期测算，并明确分期兑现与追偿/递延机制。")

    c.showPage()
    c.save()
    bio.seek(0)
    return bio

# ---------- UI ----------
st.markdown("### 石家庄装备制造产业园 — 招商项目研判（Streamlit 版）")
st.caption("前端输入主要信息 → 后端计算评分与结论 → 可导出 Word/PDF 报告")

with st.sidebar:
    st.subheader("基础设置")
    st.write("达产期（仅用于文案）")
    CONFIG["horizonMonths"]["land"] = st.number_input("征地（个月）", 12, 60, CONFIG["horizonMonths"]["land"])
    CONFIG["horizonMonths"]["existingNoPolicy"] = st.number_input("现房无政策（个月）", 6, 48, CONFIG["horizonMonths"]["existingNoPolicy"])
    CONFIG["horizonMonths"]["ownFactoryWithPolicy"] = st.number_input("自有厂房需政策（个月）", 12, 60, CONFIG["horizonMonths"]["ownFactoryWithPolicy"])
    st.write("硬指标阈值")
    CONFIG["thresholds"]["investPerMu"] = float(st.number_input("投资强度阈值（万/亩）", 0.0, 5000.0, CONFIG["thresholds"]["investPerMu"]))
    CONFIG["thresholds"]["taxPerMu"] = float(st.number_input("税收强度阈值（万/亩·年）", 0.0, 1000.0, CONFIG["thresholds"]["taxPerMu"]))

# --- 表单 ---
cols = st.columns(2)
with cols[0]:
    st.header("一、项目基本信息")
    projectName = st.text_input("项目名称", value="高端装备制造项目")
    industry = st.selectbox("产业类别", options=list(INDUSTRIES.keys()), format_func=lambda k: INDUSTRIES[k])
    projectType = st.selectbox("项目类型", options=list(PROJECT_TYPES.keys()), format_func=lambda k: PROJECT_TYPES[k])
    locationNote = st.text_input("拟选址/备注", value="科创谷/产业港X期")
    landMu = number_or_zero(st.text_input("占地（亩）", value=""))
    buildingArea = number_or_zero(st.text_input("建筑面积（㎡）", value=""))
    floorRatio = number_or_zero(st.text_input("容积率（折算用）", value=""))

    st.header("二、投资与效益")
    investTotal = number_or_zero(st.text_input("计划总投资（万元）", value="10000"))
    investEquipment = number_or_zero(st.text_input("设备投资（万元）", value="6000"))
    investCivil = number_or_zero(st.text_input("土建投资（万元）", value="3000"))
    expectedAnnualTax = number_or_zero(st.text_input("预计年税收（万元）", value="1500"))
    bankCreditReady = st.checkbox("资金已落实（自有/授信）", value=True)

with cols[1]:
    st.header("三、企业与风险")
    companyName = st.text_input("企业名称", value="某装备制造有限公司")
    establishedYear = st.text_input("成立年份", value="2015")
    registeredInLuan = st.checkbox("已在栾城区注册/将注册", value=True)

    revenuePrev = number_or_zero(st.text_input("上年营收（万元）", value="20000"))
    revenueCurr = number_or_zero(st.text_input("当年营收（万元）", value="22000"))
    taxPrev = number_or_zero(st.text_input("上年税收（万元）", value="1200"))
    taxCurr = number_or_zero(st.text_input("当年税收（万元）", value="1300"))
    netProfitPrev = number_or_zero(st.text_input("上年净利润（万元）", value="1200"))
    netProfitCurr = number_or_zero(st.text_input("当年净利润（万元）", value="1300"))
    topCustomersStable = st.checkbox("Top客户稳定/在手订单充分", value=True)

    certHighTech = st.checkbox("高新技术企业", value=True)
    certSpecTiny = st.checkbox("专精特新", value=False)
    certOtherCount = int(number_or_zero(st.text_input("其他资质/专利数量", value="1")))

    st.markdown("**一票否决（任一项为“是”建议拒绝）**")
    riskDishonest = st.checkbox("失信被执行/严重信用风险", value=False)
    riskEnvSafety = st.checkbox("重大环保/安监处罚未结", value=False)
    riskIllegalLand = st.checkbox("违法违规用地", value=False)
    riskCoreLicenseMissing = st.checkbox("核心资质缺失且短期不可补齐", value=False)

st.header("四、协同与落地")
c1, c2, c3, c4 = st.columns(4)
synergyLevel = c1.selectbox("产业协同程度", options=[2,1,0], index=1, format_func=lambda v: ["协同较弱","一般协同","显著补链/强协同"][2-v])
approvalsLevel = c2.selectbox("审批要件成熟度", options=[2,1,0], index=1, format_func=lambda v: ["尚未准备","部分具备","要件齐全"][2-v])
carrierMatch = c3.selectbox("载体匹配度", options=[2,1,0], index=1, format_func=lambda v: ["不匹配/需求不清","基本匹配","高度匹配"][2-v])
resourcesLevel = c4.selectbox("资源保障", options=[2,1,0], index=1, format_func=lambda v: ["短缺/需新建","基本满足","资源充足"][2-v])

customIntro = st.text_input("建设内容（一句话）", value="新建高精度机加工产线与装配线")

policyCoverYearsLimit = number_or_zero(st.text_input("（需政策）净新增税收覆盖期阈值（年，仅文案）", value="5"))

# 组装输入
model = ModelInput(
    projectName=projectName,
    industry=industry,
    projectType=projectType,
    locationNote=locationNote,
    landMu=landMu,
    buildingArea=buildingArea,
    floorRatio=floorRatio,
    investTotal=investTotal,
    investEquipment=investEquipment,
    investCivil=investCivil,
    expectedAnnualTax=expectedAnnualTax,
    companyName=companyName,
    establishedYear=establishedYear,
    registeredInLuan=registeredInLuan,
    revenuePrev=revenuePrev,
    revenueCurr=revenueCurr,
    taxPrev=taxPrev,
    taxCurr=taxCurr,
    netProfitPrev=netProfitPrev,
    netProfitCurr=netProfitCurr,
    topCustomersStable=topCustomersStable,
    certHighTech=certHighTech,
    certSpecTiny=certSpecTiny,
    certOtherCount=certOtherCount,
    riskDishonest=riskDishonest,
    riskEnvSafety=riskEnvSafety,
    riskIllegalLand=riskIllegalLand,
    riskCoreLicenseMissing=riskCoreLicenseMissing,
    synergyLevel=synergyLevel,
    approvalsLevel=approvalsLevel,
    carrierMatch=carrierMatch,
    resourcesLevel=resourcesLevel,
    customIntro=customIntro,
    policyCoverYearsLimit=policyCoverYearsLimit,
)

# 评估
ev = evaluate(model)

# 摘要卡片
st.markdown("---")
k1, k2, k3, k4 = st.columns(4)
k1.metric("折算亩", f"{ev['mu']:.2f} 亩")
k2.metric("投资强度", f"{ev['investIntensity']:.1f} 万/亩")
k3.metric("税收强度", f"{ev['taxIntensity']:.1f} 万/亩·年")
k4.metric("综合评分", f"{ev['total']}/100")

# 报告预览
st.markdown("### 预览 · 研判报告")
st.write(f"**结论：** :{'green' if ev['decision']=='通过/签约' else 'orange' if ev['decision']=='附条件通过' else 'gray'}[{ev['decision']}]")
if ev["reasons"]:
    st.write("**主要原因：**")
    st.write("\\n".join([f"- {r}" for r in ev["reasons"]]))
if ev["clauses"]:
    st.write("**签约/附条件条款建议：**")
    st.write("\\n".join([f"- {c}" for c in ev["clauses"]]))

with st.expander("展开查看完整报告文本"):
    st.markdown(f"""
**一、项目简介**  
{ev['autoIntro']}

- 项目类型：{PROJECT_TYPES.get(model.projectType,'')}；产业类别：{INDUSTRIES.get(model.industry,'')}
- 折算亩：{ev['mu']:.2f} 亩；投资强度：{ev['investIntensity']:.1f} 万/亩；税收强度：{ev['taxIntensity']:.1f} 万/亩·年
- 达产期参考：{ev['horizon']} 个月

**二、阈值校验与评分**  
- 硬指标阈值：投资≥{CONFIG['thresholds']['investPerMu']} 万/亩，税收≥{CONFIG['thresholds']['taxPerMu']} 万/亩·年  
- 一票否决：{"命中（" + "，".join(ev["vetoReasons"]) + "）" if ev["veto"] else "未命中"}  
- A 硬达标性：{ev['sectionScores']['A']} / 40  
- B 企业实力：{ev['sectionScores']['B']} / 30  
- C 产业协同：{ev['sectionScores']['C']} / 20  
- D 可落地与合规：{ev['sectionScores']['D']} / 10  

**三、研判结论与建议**  
- 结论：{ev['decision']}  
{"\\n".join([f"- {r}" for r in ev["reasons"]]) if ev["reasons"] else ""}
**签约/附条件条款建议：**  
{"\\n".join([f"- {c}" for c in ev["clauses"]]) if ev["clauses"] else ""}

**四、补充说明**  
若为“购园区自有厂房（需政策）”类型，需在投决前完成净新增税收覆盖期测算，并明确分期兑现与追偿/递延机制。
""")

# 导出按钮
docx_bytes = build_docx_report(model, ev)
pdf_bytes = build_pdf_report(model, ev)

left, right = st.columns(2)
with left:
    st.download_button(
        "导出 Word（DOCX）",
        data=docx_bytes,
        file_name=f"{model.projectName or '项目'}_研判报告.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
with right:
    st.download_button(
        "导出 PDF",
        data=pdf_bytes,
        file_name=f"{model.projectName or '项目'}_研判报告.pdf",
        mime="application/pdf",
    )

st.caption("口径提示：投资强度=固定资产/折算亩；税收强度=年税收/折算亩。三类项目统一口径；需政策项目须测算净新增税收覆盖期。")
