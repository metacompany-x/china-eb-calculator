# 中国大陆 EB 排期计算器

China-born EB-1 / EB-2 / EB-3 green card wait time calculator.

在线使用：https://metacompany-x.github.io/china-eb-calculator/

## 算法

1. 前面的主申请人 = 已批 I-140 积压人数 ÷ 覆盖的排期年数 × 你与当前 Final Action Date 之间的年数
2. 前面的总人数 = 主申请人 × 家属系数（EB-1 2.0、EB-2 1.6、EB-3 1.7）
3. 等待年数 = 前面的总人数 ÷ 每年给中国大陆的名额（FY2024 实际、近 3/5/7 年平均或法定下限 2,803）
4. 拿卡时间 = 排到时间 + I-485 审批时间

## 数据来源

- USCIS 已批 I-140 等待名额人数（截至 2026 年 6 月）
- 美国国务院 Report of the Visa Office, Table V（FY2018–2024 发放量）
- DHS Yearbook of Immigration Statistics FY2023, Table 7（主申请人与家属比例）
- Visa Bulletin（2026 年 11 月 Final Action Dates）

## 更新数据

所有参数在 `index.html` 底部脚本的 `CAT` 对象里：`fad`（排期线）、`backlog`（I-140 积压）、`horizon`（积压覆盖到的排期日）、`actual`/`a3`/`a5`/`a7`（每年名额）、`dep`（家属系数）。改完记得同步更新页面上的日期说明和 `sitemap.xml` 的 `lastmod`。

本工具只是估算，不构成法律意见。
