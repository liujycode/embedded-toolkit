#!/usr/bin/env python3
"""核验器量化基准（规格 §2.8）：注入集召回、正样本集误报、性能、回归集。

用例是可复核的"生成物"（幂等，生成物入库）：

  python tools/verify_bench.py generate   # 生成 tests/inject/ 与 tests/normal/ 用例 + 清单
  python tools/verify_bench.py check      # 评测：逐规则召回、误报率、性能；不达标退出码 1（CI 用）
  python tools/verify_bench.py doc        # 跑 check 并把结果写入 benchmarks/verify-recall.md
  python tools/verify_bench.py corpus --dir <目录> --svd <SVD>   # 真实代码误报统计（本地用，不写仓库）

注入集：每类注入 ≥ 20 处（规格阈值：E01–E06/E08–E10 召回 ≥ 90%，E07 ≥ 80%）。
正样本集：≥ 50 个不含注入的文件（阈值：报桶误报率 ≤ 5%）。
性能：1000 行文件核验 ≤ 2 s。
用例针对合成芯片 SYNTH32（tests/fixtures/synthetic.svd，非厂商数据）。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
SCRIPTS = os.path.join(ROOT, "skills", "embedded-register-verify", "scripts")
SYNTH = os.path.join(ROOT, "tests", "fixtures", "synthetic.svd")
INJECT_DIR = os.path.join(ROOT, "tests", "inject")
NORMAL_DIR = os.path.join(ROOT, "tests", "normal")
REGRESS_DIR = os.path.join(ROOT, "tests", "regress")
DOC = os.path.join(ROOT, "benchmarks", "verify-recall.md")

for _p in (SHARED, SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crules  # noqa: E402
from etk_core.svd import load_device  # noqa: E402

RECALL_TARGET = {
    "E01": 0.9, "E02": 0.9, "E03": 0.9, "E04": 0.9, "E05": 0.9,
    "E06": 0.9, "E07": 0.8, "E08": 0.9, "E09": 0.9, "E10": 0.9,
}
FP_TARGET = 0.05
PERF_TARGET = 2.0
PERF_LINES = 1000
IND = "    "


# ---------------------------------------------------------------- 文件组装

def _rule_file_header(rule, filename):
    return [
        "/* 自动生成：核验器注入集（规则 %s，文件 %s）。" % (rule, filename),
        "   下列每一处注入都应触发一次 %s；逐条 ground truth 见 tests/inject/manifest.json。" % rule,
        "   请勿手改：重新生成 python tools/verify_bench.py generate */",
        '#include "synth32.h"',
        "",
    ]


def build_rule_file(rule, injections, header_lines=None):
    """单文件多注入：injections = [(note, stmt)] → (相对路径, 文本, 用例清单)。"""
    slug = rule.lower()
    relpath = "tests/inject/%s_injections.c" % slug
    lines = _rule_file_header(rule, os.path.basename(relpath))
    if header_lines:
        lines.extend(header_lines)
        lines.append("")
    cases = []
    for idx, (note, stmt) in enumerate(injections, 1):
        lines.append("void %s_case_%02d(void)" % (slug, idx))
        lines.append("{")
        lines.append(IND + stmt)
        line_no = len(lines)
        lines.append("}")
        lines.append("")
        cases.append({
            "id": "%s-%02d" % (slug, idx), "rule": rule, "file": relpath,
            "line": line_no, "note": note,
        })
    return relpath, "\n".join(lines).rstrip("\n") + "\n", cases


def build_one_shot(rule, case_id, note, body, inject_at, header_lines=None):
    """单注入单文件：body 为函数体行（不含缩进）；inject_at 为期望触发行的下标。"""
    relpath = "tests/inject/%s.c" % case_id
    lines = [
        "/* 自动生成：核验器注入集（规则 %s，用例 %s）。" % (rule, case_id),
        "   预期触发一次 %s；ground truth 见 tests/inject/manifest.json。" % rule,
        "   请勿手改：重新生成 python tools/verify_bench.py generate */",
        '#include "synth32.h"',
        "",
    ]
    if header_lines:
        lines.extend(header_lines)
        lines.append("")
    lines.append("void %s(void)" % case_id.replace("-", "_"))
    lines.append("{")
    inject_line = None
    for i, item in enumerate(body):
        lines.append((IND + item) if item else "")
        if i == inject_at:
            inject_line = len(lines)
    lines.append("}")
    case = {"id": case_id, "rule": rule, "file": relpath, "line": inject_line, "note": note}
    return relpath, "\n".join(lines).rstrip("\n") + "\n", [case]


# ---------------------------------------------------------------- 各规则注入

def injections_e01():
    return [
        ("未知外设 TIM2（近似已存在的 TIM1）", "TIM2->CR1 |= 0x00000001;"),
        ("未知外设 TIM3", "TIM3->CR1 = 0x00000080;"),
        ("未知外设 TIM4", "TIM4->SR = 0x0000001F;"),
        ("未知外设 SPI1", "SPI1->CR1 = 0x00000400;"),
        ("未知外设 SPI2", "SPI2->CR2 |= 0x00000001;"),
        ("未知外设 I2C1", "I2C1->CR1 |= 0x00000001;"),
        ("未知外设 I2C2", "I2C2->OAR1 = 0x00000050;"),
        ("未知外设 ADC1", "ADC1->CR2 |= 0x00000001;"),
        ("未知外设 ADC2", "ADC2->CR2 = 0x00000001;"),
        ("未知外设 DAC1", "DAC1->CR |= 0x00000001;"),
        ("未知外设 RTC", "RTC->CRL = 0x00000001;"),
        ("未知外设 CRC", "CRC->CR = 0x00000001;"),
        ("未知外设 RNG", "RNG->CR |= 0x00000001;"),
        ("未知外设 CAN1", "CAN1->MCR |= 0x00000001;"),
        ("未知外设 WWDG", "WWDG->CR = 0x0000007F;"),
        ("未知外设 IWDG", "IWDG->KR = 0x0000CCCC;"),
        ("未知外设 UART4", "UART4->CR1 |= 0x00000001;"),
        ("未知外设 UART5", "UART5->CR1 |= 0x00000001;"),
        ("未知外设 GPIOD（同族 GPIO 存在）", "GPIOD->MODER = 0x00000001;"),
        ("未知外设 GPIOE（同族 GPIO 存在）", "GPIOE->ODR = 0x00000001;"),
        ("未知外设 SDMMC1", "SDMMC1->CLKCR |= 0x00000001;"),
        ("未知外设 ETH", "ETH->MACCR |= 0x00000001;"),
        ("未知外设 SPI3（宏形态 SET_BIT）", "SET_BIT(SPI3->CR1, 0x00000001);"),
        ("未知外设 ADC3（宏形态 WRITE_REG）", "WRITE_REG(ADC3->CR2, 0x00000001);"),
    ]


def injections_e02():
    return [
        ("USART1.CR2 不存在（SVD 只定义 CR1/BRR/SR）", "USART1->CR2 |= 0x00002000;"),
        ("USART1.CR3 不存在", "USART1->CR3 = 0x00000000;"),
        ("USART1.GTPR 不存在", "USART1->GTPR = 0x00000000;"),
        ("USART1.RQR 不存在", "USART1->RQR = 0x00000001;"),
        ("USART1.ICR 不存在", "USART1->ICR = 0x00000001;"),
        ("USART2.ISR 不存在", "USART2->ISR = 0x00000000;"),
        ("USART2.TDR 不存在", "USART2->TDR = 0x00000041;"),
        ("TIM1.CR3 不存在", "TIM1->CR3 = 0x00000000;"),
        ("TIM1.SMCR 不存在", "TIM1->SMCR = 0x00000000;"),
        ("TIM1.DIER 不存在", "TIM1->DIER = 0x00000001;"),
        ("TIM1.EGR 不存在", "TIM1->EGR = 0x00000001;"),
        ("TIM1.PSC 不存在", "TIM1->PSC = 0x0000FFFF;"),
        ("TIM1.ARR 不存在", "TIM1->ARR = 0x0000FFFF;"),
        ("GPIOA.IDR 被当输出写（SVD 未定义）", "GPIOA->IDR = 0x00000001;"),
        ("GPIOA.BSRR 不存在", "GPIOA->BSRR = 0x00000001;"),
        ("GPIOA.AFRL 不存在", "GPIOA->AFRL = 0x00000000;"),
        ("RCC.CFGR 不存在", "RCC->CFGR |= 0x00000002;"),
        ("RCC.AHB1ENR 不存在", "RCC->AHB1ENR |= 0x00000001;"),
        ("RCC.BDCR 不存在", "RCC->BDCR = 0x00000001;"),
        ("DMA1.IFCR 不存在", "DMA1->IFCR = 0x00000001;"),
        ("DMA1.CSELR 不存在", "DMA1->CSELR = 0x00000001;"),
        ("RCC.APB2ENR 不存在（宏形态）", "WRITE_REG(RCC->APB2ENR, 0x00000001);"),
    ]


def injections_e03():
    return [
        ("位域 ZZZ 不存在", "USART1->CR1 |= USART_CR1_ZZZ;"),
        ("位域 RXNE 不在 CR1", "USART1->CR1 |= USART_CR1_RXNE;"),
        ("位域 RE 不存在", "USART1->CR1 |= USART_CR1_RE;"),
        ("位域 IDLE 不存在", "USART1->CR1 |= USART_CR1_IDLE;"),
        ("位域 PE 不存在", "USART1->CR1 |= USART_CR1_PE;"),
        ("位域 TXEIE 不存在", "USART1->CR1 |= USART_CR1_TXEIE;"),
        ("位域 ABREN 不存在", "USART1->CR1 |= USART_CR1_ABREN;"),
        ("位域 SBRK 不存在（= 形态）", "USART1->CR1 = USART_CR1_SBRK;"),
        ("位域 LBDF 不存在（SET_BIT 形态）", "SET_BIT(USART1->CR1, USART_CR1_LBDF);"),
        ("位域 TXEIE 不存在（CLEAR_BIT 形态）", "CLEAR_BIT(USART1->CR1, USART_CR1_TXEIE);"),
        ("宏属于 BRR 却写在 CR1", "USART1->CR1 |= USART_BRR_DIV;"),
        ("宏属于 SR 却写在 CR1（TXE）", "USART1->CR1 |= USART_SR_TXE;"),
        ("宏属于 SR 却写在 CR1（TC）", "USART1->CR1 |= USART_SR_TC;"),
        ("宏属于 CR1 却写在 BRR", "USART1->BRR = USART_CR1_UE;"),
        ("TIM 宏属于 CR1 却写在 CR2", "TIM1->CR2 |= TIM_CR1_CEN;"),
        ("TIM 宏属于 CR2 却写在 CR1（带 _Msk）", "TIM1->CR1 |= TIM_CR2_MMS_Msk;"),
        ("TIM 宏属于 CR2 却写在 CR1（无后缀）", "TIM1->CR1 |= TIM_CR2_MMS;"),
        ("TIM 宏属于 CR1 却写在 CR2（= 形态）", "TIM1->CR2 = TIM_CR1_DIR;"),
        ("枚举名拼错 EVEEN", "USART1->CR1 |= USART_CR1_PS_EVEEN;"),
        ("枚举名拼错 OD", "USART1->CR1 |= USART_CR1_PS_OD;"),
        ("位域名后多写 PS", "USART1->CR1 |= USART_CR1_PS_PS;"),
        ("枚举名拼错（MODIFY_REG 掩码形态）", "MODIFY_REG(USART1->CR1, USART_CR1_PS_EVEEN, 0);"),
        ("位域名重复 M0_M0", "USART1->CR1 |= USART_CR1_M0_M0;"),
        ("枚举名拼错 ODDD（WRITE_REG 形态）", "WRITE_REG(USART1->CR1, USART_CR1_PS_ODDD);"),
    ]


def injections_e04():
    return [
        ("TIM1.CR1 16 位溢出（=）", "TIM1->CR1 = 0x00010000;"),
        ("TIM1.CR1 16 位溢出（|=）", "TIM1->CR1 |= 0x00010000;"),
        ("TIM1.CR1 边界外 0x1FFFF", "TIM1->CR1 = 0x0001FFFF;"),
        ("TIM1.CR1S（派生寄存器）同样 16 位", "TIM1->CR1S = 0x00010000;"),
        ("GPIOA.ODR 16 位溢出", "GPIOA->ODR = 0x00010000;"),
        ("GPIOB.ODR 16 位溢出（|=）", "GPIOB->ODR |= 0x00018000;"),
        ("GPIOC.ODR 16 位溢出（0xFFFF1）", "GPIOC->ODR = 0x000FFFF1;"),
        ("USART1.CR1 32 位溢出", "USART1->CR1 = 0x100000000;"),
        ("USART1.BRR 32 位溢出（|=）", "USART1->BRR |= 0x800000000;"),
        ("MODIFY_REG 位域溢出 0x8（MMS 3 位）", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x8);"),
        ("MODIFY_REG 位域溢出 0x9", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x9);"),
        ("MODIFY_REG 位域溢出 0xA", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xA);"),
        ("MODIFY_REG 位域溢出 0xB", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xB);"),
        ("MODIFY_REG 位域溢出 0xC", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xC);"),
        ("MODIFY_REG 位域溢出 0xD", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xD);"),
        ("MODIFY_REG 位域溢出 0xE", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xE);"),
        ("MODIFY_REG 位域溢出 0xF", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0xF);"),
        ("SET_BIT 数值超过寄存器宽度", "SET_BIT(TIM1->CR1, 0x00010000);"),
        ("WRITE_REG 数值超过寄存器宽度", "WRITE_REG(TIM1->CR1, 0x00010000);"),
        ("CLEAR_BIT 数值超过寄存器宽度", "CLEAR_BIT(TIM1->CR1, 0x00010000);"),
        ("MODIFY_REG 置位值超位域（单宏掩码）", "MODIFY_REG(TIM1->CR1, TIM_CR1_CEN, 0x00010000);"),
        ("MODIFY_REG 置位值超寄存器宽度（多宏掩码）", "MODIFY_REG(TIM1->CR1, TIM_CR1_CEN | TIM_CR1_DIR, 0x00020000);"),
        ("MODIFY_REG 置位值超位域（GPIO MODE0）", "MODIFY_REG(GPIOA->MODER, GPIO_MODER_MODE0_Msk, 0x00010000);"),
        ("TIM1.CR2.MMS 位域直写溢出 0x8（3 位）", "TIM1->CR2.MMS = 0x8;"),
    ]


def injections_e05():
    return [
        ("MMS=0x2 不是枚举（0/1/1xx）", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x2);"),
        ("MMS=0x3 不是枚举", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x3);"),
        ("十进制 2", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 2);"),
        ("十进制 3", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 3);"),
        ("二进制 0b10", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0b10);"),
        ("二进制 0b11", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0b11);"),
        ("表达式 (0x1 + 0x1)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x1 + 0x1));"),
        ("表达式 (0x1 + 0x2)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x1 + 0x2));"),
        ("表达式 (0x4 >> 1)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x4 >> 1));"),
        ("表达式 (0x6 >> 1)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x6 >> 1));"),
        ("表达式 (0x3 & 0x3)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x3 & 0x3));"),
        ("表达式 (0x7 & 0x2)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x7 & 0x2));"),
        ("表达式 ~(~0x2)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, ~(~0x2));"),
        ("后缀字面量 2U", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 2U);"),
        ("掩码写法 _MASK", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_MASK, 0x2);"),
        ("取模表达式 (0x7 % 5)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (0x7 % 5));"),
        ("文件内宏 BAD_MMS=0x2", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, BAD_MMS);"),
        ("文件内宏 BAD_MMS_2=(0x1+0x2)", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, BAD_MMS_2);"),
        ("强制转型 (int)0x2", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, (int)0x2);"),
        ("位与表达式 0x1F & 0x2", "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x1F & 0x2);"),
        ("MMS 位域直写非枚举 0x2", "TIM1->CR2.MMS = 0x2;"),
        ("MMS 位域直写非枚举 0x3", "TIM1->CR2.MMS = 0x3;"),
    ]


def injections_e06():
    return [
        ("CLEAR_BIT USART1.CR1.TE", "CLEAR_BIT(USART1->CR1, USART_CR1_TE);"),
        ("CLEAR_BIT USART1.CR1.PS", "CLEAR_BIT(USART1->CR1, USART_CR1_PS);"),
        ("CLEAR_BIT USART1.CR1.OVER8", "CLEAR_BIT(USART1->CR1, USART_CR1_OVER8);"),
        ("CLEAR_BIT USART2.CR1.UE", "CLEAR_BIT(USART2->CR1, USART_CR1_UE);"),
        ("CLEAR_BIT USART2.CR1.M0", "CLEAR_BIT(USART2->CR1, USART_CR1_M0);"),
        ("CLEAR_BIT USART3.CR1.TE", "CLEAR_BIT(USART3->CR1, USART_CR1_TE);"),
        ("CLEAR_BIT USART3.CR1.M0", "CLEAR_BIT(USART3->CR1, USART_CR1_M0);"),
        ("CLEAR_BIT TIM1.CR1.CEN", "CLEAR_BIT(TIM1->CR1, TIM_CR1_CEN);"),
        ("CLEAR_BIT TIM1.CR2.MMS（_Msk）", "CLEAR_BIT(TIM1->CR2, TIM_CR2_MMS_Msk);"),
        ("CLEAR_BIT GPIOA.ODR.OD0", "CLEAR_BIT(GPIOA->ODR, GPIO_ODR_OD0);"),
        ("CLEAR_BIT GPIOB.ODR.OD0", "CLEAR_BIT(GPIOB->ODR, GPIO_ODR_OD0);"),
        ("CLEAR_BIT EXTI.PR.P0", "CLEAR_BIT(EXTI->PR, EXTI_PR_P0);"),
        ("CLEAR_BIT EXTI.PR.P1", "CLEAR_BIT(EXTI->PR, EXTI_PR_P1);"),
        ("CLEAR_BIT RCC.APB1ENR.I2C1EN", "CLEAR_BIT(RCC->APB1ENR, RCC_APB1ENR_I2C1EN);"),
        ("CLEAR_BIT TIM1.CR1.DIR", "CLEAR_BIT(TIM1->CR1, TIM_CR1_DIR);"),
        ("CLEAR_BIT USART3.CR1.PS", "CLEAR_BIT(USART3->CR1, USART_CR1_PS);"),
        ("&= ~ USART1.CR1.UE", "USART1->CR1 &= ~USART_CR1_UE;"),
        ("&= ~ USART2.CR1.TE", "USART2->CR1 &= ~USART_CR1_TE;"),
        ("&= ~ TIM1.CR1.DIR", "TIM1->CR1 &= ~TIM_CR1_DIR;"),
        ("&= ~ GPIOC.ODR.OD0", "GPIOC->ODR &= ~GPIO_ODR_OD0;"),
        ("&= ~ USART3.CR1.OVER8", "USART3->CR1 &= ~USART_CR1_OVER8;"),
        ("&= ~ RCC.APB1ENR.I2C1EN", "RCC->APB1ENR &= ~RCC_APB1ENR_I2C1EN;"),
        ("&= ~ USART2.CR1.OVER8", "USART2->CR1 &= ~USART_CR1_OVER8;"),
        ("&= ~ EXTI.PR.P0", "EXTI->PR &= ~EXTI_PR_P0;"),
    ]


def e07_specs():
    specs = []

    def add(note, body, inject_at=0, header=None):
        specs.append({
            "id": "e07-%02d" % (len(specs) + 1), "note": note, "body": list(body),
            "inject_at": inject_at, "header": list(header or []),
        })

    baud_define = ["#define UART_BAUD_VALUE 0x0683UL"]
    add("|= 写 CR1（基线，无任何使能）", ["USART2->CR1 |= USART_CR1_UE;"])
    add("= 写 CR1（宏组合值）", ["USART2->CR1 = USART_CR1_TE | USART_CR1_PS_ODD;"])
    add("写 BRR 波特率", ["USART2->BRR = 0x00000683;"])
    add("SET_BIT 形态", ["SET_BIT(USART2->CR1, USART_CR1_UE);"])
    add("MODIFY_REG 形态", ["MODIFY_REG(USART2->CR1, USART_CR1_TE, 0);"])
    add("CLEAR_BIT 形态（同时 E06）", ["CLEAR_BIT(USART2->CR1, USART_CR1_UE);"])
    add("WRITE_REG 形态", ["WRITE_REG(USART2->CR1, 0x00000001);"])
    add("数值 |= 写", ["USART2->CR1 |= 0x00000001;"])
    add("移位表达式", ["USART2->CR1 |= (0x1 << 0);"])
    add("文件内宏作波特率（|=）", ["USART2->BRR |= UART_BAUD_VALUE;"], header=baud_define)
    add("先写 RCC 但只开 HSION（不是 USART2EN）",
        ["RCC->CR |= RCC_CR_HSION;", "USART2->CR1 |= USART_CR1_UE;"], inject_at=1)
    add("HAL 使能的是 USART1（不是 USART2）",
        ["__HAL_RCC_USART1_CLK_ENABLE();", "USART2->CR1 |= USART_CR1_UE;"], inject_at=1)
    add("两处 USART2 写入（首行报）",
        ["USART2->CR1 |= USART_CR1_UE;", "USART2->CR1 |= USART_CR1_TE;"])
    add("GPIO 写在前（GPIO 无使能位）",
        ["GPIOA->MODER = 0x00000001;", "USART2->CR1 |= USART_CR1_TE;"], inject_at=1)
    add("TIM1 写在前（TIM1 无使能位）",
        ["TIM1->CR1 |= TIM_CR1_CEN;", "USART2->CR1 |= USART_CR1_TE;"], inject_at=1)
    add("写 USART2.SR（只读，同时 E10）", ["USART2->SR = 0x00000040;"])
    add("&= ~ 清位形态（同时 E06）", ["USART2->CR1 &= ~USART_CR1_TE;"])
    add("^= 形态", ["USART2->CR1 ^= USART_CR1_TE;"])
    add("写 M0", ["USART2->CR1 |= USART_CR1_M0;"])
    add("箭头前有空格（词法容错）", ["USART2 ->CR1 |= USART_CR1_UE;"])
    add("文件内宏作 BRR 值（=）", ["USART2->BRR = UART_BAUD_VALUE;"], header=baud_define)
    add("MODIFY_REG 置位同名掩码", ["MODIFY_REG(USART2->CR1, USART_CR1_UE, USART_CR1_UE);"])
    return specs


def e09_specs():
    specs = []
    bodies = [
        ("两处相同分组（3, 3）", ["NVIC_SetPriorityGrouping(3);", "NVIC_SetPriorityGrouping(3);"]),
        ("两处不同分组（3, 4）", ["NVIC_SetPriorityGrouping(3);", "NVIC_SetPriorityGrouping(4);"]),
        ("两处相同分组（4, 4）", ["NVIC_SetPriorityGrouping(4);", "NVIC_SetPriorityGrouping(4);"]),
        ("两处不同分组（0, 7）", ["NVIC_SetPriorityGrouping(0);", "NVIC_SetPriorityGrouping(7);"]),
        ("两处相同分组（2, 2）", ["NVIC_SetPriorityGrouping(2);", "NVIC_SetPriorityGrouping(2);"]),
        ("三处分组（3, 3, 3）", ["NVIC_SetPriorityGrouping(3);", "NVIC_SetPriorityGrouping(3);",
                                 "NVIC_SetPriorityGrouping(3);"]),
        ("两处之间空行", ["NVIC_SetPriorityGrouping(3);", "", "NVIC_SetPriorityGrouping(3);"]),
        ("两处之间注释", ["NVIC_SetPriorityGrouping(3);", "/* 复制粘贴留下的第二处 */",
                          "NVIC_SetPriorityGrouping(3);"]),
        ("无符号后缀（3U, 3U）", ["NVIC_SetPriorityGrouping(3U);", "NVIC_SetPriorityGrouping(3U);"]),
        ("括号内空格（ 3 ）", ["NVIC_SetPriorityGrouping( 3 );", "NVIC_SetPriorityGrouping(3);"]),
        ("函数名与括号间空格", ["NVIC_SetPriorityGrouping (3);", "NVIC_SetPriorityGrouping(3);"]),
        ("两处不同分组（3, 5）", ["NVIC_SetPriorityGrouping(3);", "NVIC_SetPriorityGrouping(5);"]),
        ("两处不同分组（5, 3）", ["NVIC_SetPriorityGrouping(5);", "NVIC_SetPriorityGrouping(3);"]),
        ("三处分组（0, 1, 2）", ["NVIC_SetPriorityGrouping(0);", "NVIC_SetPriorityGrouping(1);",
                                 "NVIC_SetPriorityGrouping(2);"]),
        ("注释行后两处（3, 4）", ["/* 初始化中断分组 */", "NVIC_SetPriorityGrouping(3);",
                                  "NVIC_SetPriorityGrouping(4);"]),
        ("两处相同分组（7, 7）", ["NVIC_SetPriorityGrouping(7);", "NVIC_SetPriorityGrouping(7);"]),
        ("两处不同分组（2, 6）", ["NVIC_SetPriorityGrouping(2);", "NVIC_SetPriorityGrouping(6);"]),
        ("两处之间夹寄存器写", ["NVIC_SetPriorityGrouping(3);", "TIM1->CR1 |= TIM_CR1_CEN;",
                                "NVIC_SetPriorityGrouping(4);"]),
        ("空行与注释分隔（2, 2）", ["NVIC_SetPriorityGrouping(2);", "", "/* 又一个 */",
                                    "NVIC_SetPriorityGrouping(2);"]),
        ("两处相同分组（6, 6）", ["NVIC_SetPriorityGrouping(6);", "NVIC_SetPriorityGrouping(6);"]),
        ("行尾注释（3, 3）", ["NVIC_SetPriorityGrouping(3); /* app */",
                              "NVIC_SetPriorityGrouping(3);"]),
        ("两处相同分组（1, 1）", ["NVIC_SetPriorityGrouping(1);", "NVIC_SetPriorityGrouping(1);"]),
    ]
    for idx, (note, body) in enumerate(bodies, 1):
        inject_at = next(i for i, item in enumerate(body) if "NVIC_SetPriorityGrouping" in item)
        specs.append({
            "id": "e09-%02d" % idx, "note": note, "body": body,
            "inject_at": inject_at, "header": [],
        })
    return specs


def injections_e08():
    return [
        ("已知地址 USART1.CR1", "*(volatile uint32_t *)0x40013800 = 0x00000001;"),
        ("已知地址 USART1.BRR", "*(volatile uint32_t *)0x4001380C = 0x00000683;"),
        ("已知地址 USART2.CR1", "*(uint32_t *)0x40004400 = 0x00000001;"),
        ("已知地址 USART2.BRR", "*(volatile uint32_t *)0x4000440C = 0x00000001;"),
        ("已知地址 GPIOA.MODER", "*(volatile uint32_t *)0x48000000 = 0x00000001;"),
        ("已知地址 GPIOB.MODER", "*(volatile uint32_t *)0x48000400 = 0x00000001;"),
        ("已知地址 GPIOC.ODR", "*(volatile uint32_t *)0x48000814 = 0x00000001;"),
        ("已知地址 TIM1.CR1", "*(volatile uint32_t *)0x40012C00 = 0x00000041;"),
        ("已知地址 TIM1.CR2", "*(volatile uint32_t *)0x40012C04 = 0x00000001;"),
        ("已知地址 RCC.APB1ENR", "*(volatile uint32_t *)0x40021058 = 0x00000001;"),
        ("已知地址 DMA1.ISR", "*(volatile uint32_t *)0x40020000 = 0x00000001;"),
        ("已知地址 EXTI.PR（__IO 写法）", "*(__IO uint32_t *)0x40010414 = 0x00000001;"),
        ("已知地址 RCC.CR", "*(volatile uint32_t *)0x40021000 = 0x00000001;"),
        ("未知地址 USART1 偏移 +4（寄存器间隙）", "*(volatile uint32_t *)0x40013804 = 0x00000001;"),
        ("未知地址 USART2 偏移 +4", "*(volatile uint32_t *)0x40004404 = 0x00000001;"),
        ("未知地址 TIM1 偏移 0x50", "*(volatile uint32_t *)0x40012C50 = 0x00000001;"),
        ("未知地址 0xDEAD0000", "*(volatile uint32_t *)0xDEAD0000 = 0x00000001;"),
        ("未知地址 0xDEADBEEF", "*(volatile uint32_t *)0xDEADBEEF = 0x00000001;"),
        ("未知地址 0x20000000（SRAM 区）", "*(volatile uint32_t *)0x20000000 = 0x00000001;"),
        ("未知地址 0x40000000", "*(volatile uint32_t *)0x40000000 = 0x00000001;"),
        ("未知地址 0xFFFFF000", "*(volatile uint32_t *)0xFFFFF000 = 0x00000001;"),
        ("未知地址 0x48004000（GPIO 区之外）", "*(uint32_t *)0x48004000 = 0x00000001;"),
    ]


def injections_e10():
    return [
        ("USART1.SR 只读寄存器（=）", "USART1->SR = 0x00000020;"),
        ("USART1.SR 只读寄存器（|=）", "USART1->SR |= 0x00000040;"),
        ("USART1.SR 只读寄存器（&= ~）", "USART1->SR &= ~0x00000040;"),
        ("USART1.SR 只读寄存器（SET_BIT）", "SET_BIT(USART1->SR, 0x00000020);"),
        ("USART1.SR 只读寄存器（CLEAR_BIT）", "CLEAR_BIT(USART1->SR, USART_SR_TXE);"),
        ("TIM1.CNT 只读寄存器（=）", "TIM1->CNT = 0x00000010;"),
        ("TIM1.CNT 只读寄存器（|=）", "TIM1->CNT |= 0x00000001;"),
        ("TIM1.CNT 只读寄存器（WRITE_REG）", "WRITE_REG(TIM1->CNT, 0x00000010);"),
        ("TIM1.CNT 只读寄存器（SET_BIT）", "SET_BIT(TIM1->CNT, 0x00000001);"),
        ("TIM1.CNT 只读寄存器（MODIFY_REG）", "MODIFY_REG(TIM1->CNT, 0x0000FFFF, 0x00000010);"),
        ("RCC.CR 只读位 HSIRDY（宏 |=）", "RCC->CR |= RCC_CR_HSIRDY;"),
        ("RCC.CR 只读位 HSIRDY（数值 =）", "RCC->CR = 0x00000400;"),
        ("RCC.CR 只读位 HSIRDY（数值 |=）", "RCC->CR |= 0x00000400;"),
        ("RCC.CR 只读位 HSIRDY（移位表达式）", "RCC->CR |= (1 << 10);"),
        ("RCC.CR 只读位 HSIRDY（1U 后缀）", "RCC->CR |= (1U << 10);"),
        ("RCC.CR 只读位 HSIRDY（SET_BIT 宏）", "SET_BIT(RCC->CR, RCC_CR_HSIRDY);"),
        ("RCC.CR 只读位 HSIRDY（SET_BIT 数值）", "SET_BIT(RCC->CR, 0x00000400);"),
        ("RCC.CR 只读位 HSIRDY（WRITE_REG 数值）", "WRITE_REG(RCC->CR, 0x00000400);"),
        ("RCC.CR 只读位 HSIRDY（MODIFY_REG 宏）",
         "MODIFY_REG(RCC->CR, RCC_CR_HSIRDY, RCC_CR_HSIRDY);"),
        ("RCC.CR 只读位 HSIRDY（MODIFY_REG 数值置位）",
         "MODIFY_REG(RCC->CR, 0x0000FFFF, 0x00000400);"),
        ("RCC.CR 写入等于复位值 0x500（同时含只读位）", "RCC->CR = 0x00000500;"),
        ("RCC.CR 只读位混在宏组合里", "RCC->CR |= RCC_CR_HSION | RCC_CR_HSIRDY;"),
        ("RCC.CR 只读位直写（REG.FIELD）", "RCC->CR.HSIRDY = 1;"),
    ]


# ---------------------------------------------------------------- 正样本集

def normal_specs():
    specs = []

    def add(cid, note, body, header=None):
        specs.append({"id": cid, "note": note, "body": list(body), "header": list(header or [])})

    baud = "#define UART_BAUD_VALUE 0x0683UL"

    # A. USART 初始化（10）
    add("n01", "USART2：RCC 置位 + 宏 |= 初始化", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE | USART_CR1_TE | USART_CR1_PS_ODD;",
        "USART2->BRR = 0x00000683;",
    ])
    add("n02", "USART2：HAL 使能宏 + = 宏组合值", [
        "__HAL_RCC_USART2_CLK_ENABLE();",
        "USART2->CR1 = USART_CR1_UE | USART_CR1_TE;",
        "USART2->BRR = 0x00000683;",
    ])
    add("n03", "USART2：SET_BIT/MODIFY_REG + 文件内宏", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "SET_BIT(USART2->CR1, USART_CR1_UE);",
        "MODIFY_REG(USART2->CR1, USART_CR1_TE, USART_CR1_TE);",
        "USART2->BRR |= UART_BAUD_VALUE;",
    ], header=[baud])
    add("n04", "USART2：轮询读 SR + 写 BRR", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "while ((USART2->SR & USART_SR_TXE) == 0) { }",
        "USART2->BRR = UART_BAUD_VALUE;",
    ], header=[baud])
    add("n05", "USART1：无使能位字段，宏组合", [
        "USART1->CR1 |= USART_CR1_UE | USART_CR1_TE | USART_CR1_PS_ODD;",
        "USART1->BRR = 0x00000683;",
    ])
    add("n06", "USART3：CR1 + BRR", [
        "USART3->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART3->BRR = 0x00000683;",
    ])
    add("n07", "USART2：数值 |= 初始化", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= 0x00000009;",
        "USART2->BRR = 0x00000683;",
    ])
    add("n08", "USART1：PS 枚举名 + 读 SR 条件写", [
        "USART1->CR1 |= USART_CR1_UE | USART_CR1_PS_EVEN;",
        "uint32_t sr = USART1->SR;",
        "if (sr & USART_SR_TXE) { USART1->BRR = 0x00000683; }",
    ])
    add("n09", "USART2：宏与数值混合", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "USART2->CR1 |= 0x00000008;",
        "USART2->BRR = 0x00000683;",
    ])
    add("n10", "USART3：SET_BIT + BRR 字面量", [
        "SET_BIT(USART3->CR1, USART_CR1_UE);",
        "USART3->BRR = 0x00000683;",
    ])

    # B. GPIO（8）
    add("n11", "GPIOA：SET_BIT MODER", ["SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);"])
    add("n12", "GPIOA：MODIFY_REG MODER=OUTPUT（数值）", [
        "MODIFY_REG(GPIOA->MODER, GPIO_MODER_MODE0_Msk, 0x00000001);",
    ])
    add("n13", "GPIOB：MODIFY_REG MODER=ANALOG（数值 3）", [
        "MODIFY_REG(GPIOB->MODER, GPIO_MODER_MODE0_Msk, 0x00000003);",
    ])
    add("n14", "GPIOA：ODR 字面量 + |=", [
        "GPIOA->ODR = 0x000000FF;",
        "GPIOA->ODR |= 0x00000100;",
    ])
    add("n15", "GPIOA：SET/CLEAR 配对", [
        "SET_BIT(GPIOA->ODR, GPIO_ODR_OD0);",
        "CLEAR_BIT(GPIOA->ODR, GPIO_ODR_OD0);",
    ])
    add("n16", "GPIOA：&= ~ 清位（先置位）", [
        "SET_BIT(GPIOA->ODR, GPIO_ODR_OD0);",
        "GPIOA->ODR &= ~GPIO_ODR_OD0;",
    ])
    add("n17", "GPIOC：ODR 异或翻转", ["GPIOC->ODR ^= 0x00000001;"])
    add("n18", "GPIOB：SET_BIT ODR（另一端口）", ["SET_BIT(GPIOB->ODR, GPIO_ODR_OD0);"])

    # C. TIM（8）
    add("n19", "TIM1：|= CEN", ["TIM1->CR1 |= TIM_CR1_CEN;"])
    add("n20", "TIM1：MODIFY_REG MMS 枚举宏名", [
        "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);",
    ])
    add("n21", "TIM1：MODIFY_REG MMS 数值 1（ENABLE）", [
        "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x00000001);",
    ])
    add("n22", "TIM1：MODIFY_REG MMS 数值 4（1xx 模式）", [
        "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x00000004);",
    ])
    add("n23", "TIM1：CEN 置位后 &= ~ 清位", [
        "TIM1->CR1 |= TIM_CR1_CEN;",
        "TIM1->CR1 &= ~TIM_CR1_CEN;",
    ])
    add("n24", "TIM1：CR1 = CEN|DIR（数值）", ["TIM1->CR1 = 0x00000041;"])
    add("n25", "TIM1：CR2 |= MMS 位（0x10）", ["TIM1->CR2 |= 0x00000010;"])
    add("n26", "TIM1：MODIFY_REG MMS 数值 7（1xx 模式）", [
        "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, 0x00000007);",
    ])

    # D. EXTI / NVIC / 内核（6）
    add("n27", "EXTI：W1C 清挂起 + 分组一次 + 使能中断", [
        "EXTI->PR = EXTI_PR_P0;",
        "NVIC_SetPriorityGrouping(3);",
        "NVIC_EnableIRQ(USART1_IRQn);",
    ])
    add("n28", "EXTI：|= 置挂起位（掩码组合）", ["EXTI->PR |= EXTI_PR_P0 | EXTI_PR_P1;"])
    add("n29", "NVIC：ISER0 写 + 分组一次", [
        "NVIC->ISER0 = 0x00000001;",
        "NVIC_SetPriorityGrouping(3);",
    ])
    add("n30", "NVIC：ICPR0 清挂起", ["NVIC->ICPR0 = 0x00000001;"])
    add("n31", "SysTick：内核外设写（允许未判定）", [
        "SysTick->LOAD = 0x000FFFFF;",
        "SysTick->VAL = 0x00000000;",
        "SysTick->CTRL = 0x00000005;",
    ])
    add("n32", "内核写 + 分组一次 + 外设写", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "NVIC_SetPriorityGrouping(3);",
        "SysTick->CTRL = 0x00000005;",
    ])

    # E. 混合风格（6）
    add("n33", "DMA 簇命名（允许未判定）+ 寄存器写（先配置后使能，E11 正确顺序）", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "DMA1_Channel1->CNDTR = 0x00000100;",
        "DMA1_Channel1->CCR |= 0x00000001;",
    ])
    add("n34", "局部指针写（按惯例静默忽略）", [
        "uart->CR1 |= USART_CR1_UE;",
        "uart->BRR = 0x00000683;",
    ])
    add("n35", "HAL 函数调用为主（不产生写入）", [
        "HAL_UART_Init(&huart2);",
        "HAL_GPIO_WritePin(GPIOA, 0x0020, 1);",
    ])
    add("n36", "读状态 + 条件写 BRR", [
        "uint32_t sr = USART1->SR;",
        "if (sr & USART_SR_TXE) { USART1->BRR = 0x00000683; }",
    ])
    add("n37", "外设混合：USART2 + GPIO + TIM1", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);",
        "TIM1->CR1 |= TIM_CR1_CEN;",
        "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);",
    ])
    add("n38", "寄存器宏 + 文件内常量", [
        "USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART1->BRR = UART_BAUD_VALUE;",
    ], header=[baud])

    # F. 写入等于复位值（4，仅进清单不进报）
    add("n39", "CR1 写复位值 0（芯片默认）", ["USART1->CR1 = 0x00000000;"])
    add("n40", "ODR 写复位值 0", ["GPIOA->ODR = 0x00000000;"])
    add("n41", "APB1ENR 写复位值 0", ["RCC->APB1ENR = 0x00000000;"])
    add("n42", "TIM1.CR2 写复位值 0", ["TIM1->CR2 = 0x00000000;"])

    # G. 先置后清（4）
    add("n43", "CEN 置位后 CLEAR_BIT", [
        "TIM1->CR1 |= TIM_CR1_CEN;",
        "CLEAR_BIT(TIM1->CR1, TIM_CR1_CEN);",
    ])
    add("n44", "M0 置位后 CLEAR_BIT", [
        "USART1->CR1 |= USART_CR1_M0;",
        "CLEAR_BIT(USART1->CR1, USART_CR1_M0);",
    ])
    add("n45", "OD0 置位后 &= ~", [
        "SET_BIT(GPIOB->ODR, GPIO_ODR_OD0);",
        "GPIOB->ODR &= ~GPIO_ODR_OD0;",
    ])
    add("n46", "USART2.UE 置位后 &= ~", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "USART2->CR1 &= ~USART_CR1_UE;",
    ])

    # H. 长组合（8）
    add("n47", "完整初始化序列（多外设 + 读 + 中断）", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART2->BRR = 0x00000683;",
        "SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);",
        "TIM1->CR1 |= TIM_CR1_CEN;",
        "EXTI->PR = EXTI_PR_P0;",
        "NVIC_SetPriorityGrouping(3);",
        "NVIC_EnableIRQ(USART1_IRQn);",
    ])
    add("n48", "条件分支写（if/else）", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "if (RCC->CR & RCC_CR_HSION) { USART2->BRR = 0x00000683; }",
        "else { USART2->BRR = 0x00000341; }",
        "USART2->CR1 |= USART_CR1_UE;",
    ])
    add("n49", "两个函数：init + set_baud", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART2->BRR = 0x00000683;",
        "/* ---- */",
        "USART2->BRR = 0x00000341;",
    ])
    add("n50", "注释密集（含伪代码与寄存器名的注释）", [
        "/* 配置过程：先开时钟（RCC.APB1ENR.USART2EN），再写 CR1 */",
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN; // 打开 USART2 时钟",
        "USART2->CR1 |= USART_CR1_UE | USART_CR1_TE; /* UE=1 TE=1 */",
        "USART2->BRR = 0x00000683;",
    ])
    add("n51", "宏计算 BRR 值", [
        "#define PCLK1_HZ 42000000UL",
        "#define BAUDRATE 115200UL",
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "USART2->BRR = PCLK1_HZ / BAUDRATE;",
    ])
    add("n52", "双通道：USART1 + USART3", [
        "USART1->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART1->BRR = 0x00000683;",
        "USART3->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "USART3->BRR = 0x00000683;",
    ])
    add("n53", "GPIO 批量：ODR 多引脚", [
        "GPIOA->ODR = 0x000000FF;",
        "GPIOB->ODR = 0x0000FF00;",
        "SET_BIT(GPIOC->ODR, GPIO_ODR_OD0);",
        "GPIOC->ODR |= 0x00000100;",
    ])
    add("n54", "混合：内核写 + 簇命名 + HAL 调用 + 正常写", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "USART2->CR1 |= USART_CR1_UE;",
        "SysTick->CTRL = 0x00000005;",
        "DMA1_Channel2->CCR |= 0x00000001;",
        "HAL_UART_Init(&huart2);",
        "NVIC_SetPriorityGrouping(3);",
    ])
    add("n55", "Nordic 别名约定：NRF_ 前缀（实机为 NRF_USBD→USBD 等）", [
        "RCC->APB1ENR |= RCC_APB1ENR_USART2EN;",
        "NRF_USART2->CR1 |= USART_CR1_UE | USART_CR1_TE;",
        "NRF_USART2->BRR = 0x00000683;",
    ])
    return specs


# ---------------------------------------------------------------- 生成与判定

def build_inject():
    files = {}
    cases = []
    for rule, injections, header in (
        ("E01", injections_e01(), None),
        ("E02", injections_e02(), None),
        ("E03", injections_e03(), None),
        ("E04", injections_e04(), None),
        ("E05", injections_e05(), ["#define BAD_MMS 0x2", "#define BAD_MMS_2 (0x1 + 0x2)"]),
        ("E06", injections_e06(), ["RCC->APB1ENR |= RCC_APB1ENR_USART2EN;"]),
        ("E08", injections_e08(), ["RCC->APB1ENR |= RCC_APB1ENR_USART2EN;"]),
        ("E10", injections_e10(), None),
    ):
        relpath, text, new_cases = build_rule_file(rule, injections, header)
        files[relpath] = text
        cases.extend(new_cases)
    for rule, spec_list in (("E07", e07_specs()), ("E09", e09_specs())):
        for spec in spec_list:
            relpath, text, new_cases = build_one_shot(
                rule, spec["id"], spec["note"], spec["body"], spec["inject_at"], spec.get("header"))
            files[relpath] = text
            cases.extend(new_cases)
    manifest = {
        "kind": "verify-inject",
        "version": 1,
        "device": "SYNTH32（合成芯片；tests/fixtures/synthetic.svd）",
        "generator": "python tools/verify_bench.py generate",
        "note": "每一处注入对应一条 ground truth：期望该行触发该规则（class 与行号都必须命中）。",
        "cases": cases,
    }
    return files, manifest


def build_normal():
    files = {}
    entries = []
    for spec in normal_specs():
        relpath = "tests/normal/%s.c" % spec["id"]
        lines = [
            "/* 自动生成：核验器正样本集（%s）。" % spec["id"],
            "   预期：0 条“报”（“未判定”“芯片默认”允许，且计入统计）。",
            "   请勿手改：重新生成 python tools/verify_bench.py generate */",
            '#include "synth32.h"',
            "",
        ]
        if spec.get("header"):
            lines.extend(spec["header"])
            lines.append("")
        lines.append("void %s(void)" % spec["id"].replace("-", "_"))
        lines.append("{")
        for item in spec["body"]:
            lines.append((IND + item) if item else "")
        lines.append("}")
        files[relpath] = "\n".join(lines).rstrip("\n") + "\n"
        entries.append({"id": spec["id"], "file": relpath, "note": spec["note"]})
    manifest = {
        "kind": "verify-normal",
        "version": 1,
        "device": "SYNTH32（合成芯片；tests/fixtures/synthetic.svd）",
        "generator": "python tools/verify_bench.py generate",
        "note": "预期每个文件 0 条“报”；未判定/芯片默认不视为误报，单独统计。",
        "files": entries,
    }
    return files, manifest


def build_perf_case():
    lines = ['#include "synth32.h"', ""]
    i = 0
    while len(lines) < PERF_LINES:
        i += 1
        lines.append("void perf_%d(void)" % i)
        lines.append("{")
        lines.extend([
            "USART1->CR1 |= USART_CR1_UE;",
            "USART1->CR1 |= USART_CR1_TE;",
            "USART1->BRR = 0x00000683;",
            "if (USART1->SR & USART_SR_TXE) { USART1->BRR = 0x00000683; }",
            "SET_BIT(GPIOA->MODER, GPIO_MODER_MODE0);",
            "GPIOA->ODR = 0x000000FF;",
            "MODIFY_REG(TIM1->CR2, TIM_CR2_MMS_Msk, TIM_CR2_MMS_ENABLE);",
            "TIM1->CR1 &= ~TIM_CR1_CEN;",
            "}",
            "",
        ])
    return "\n".join(lines) + "\n"


def write_all():
    written = []
    files, inject_manifest = build_inject()
    normal_files, normal_manifest = build_normal()
    for relpath, text in list(files.items()) + list(normal_files.items()):
        path = os.path.join(ROOT, relpath)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        written.append(relpath)
    for path, manifest in ((os.path.join(INJECT_DIR, "manifest.json"), inject_manifest),
                           (os.path.join(NORMAL_DIR, "manifest.json"), normal_manifest)):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        written.append(os.path.relpath(path, ROOT).replace("\\", "/"))
    return written, len(inject_manifest["cases"]), len(normal_manifest["files"])


def drift_issues():
    issues = []
    files, inject_manifest = build_inject()
    normal_files, normal_manifest = build_normal()
    for relpath, text in list(files.items()) + list(normal_files.items()):
        path = os.path.join(ROOT, relpath)
        if not os.path.isfile(path):
            issues.append("缺少用例文件：%s" % relpath)
            continue
        with open(path, encoding="utf-8") as fh:
            actual = fh.read()
        if actual != text:
            issues.append("用例文件与生成器不一致：%s" % relpath)
    for relpath, expected in (
        ("tests/inject/manifest.json", inject_manifest),
        ("tests/normal/manifest.json", normal_manifest),
    ):
        path = os.path.join(ROOT, relpath)
        if not os.path.isfile(path):
            issues.append("缺少清单：%s" % relpath)
            continue
        with open(path, encoding="utf-8") as fh:
            try:
                actual = json.load(fh)
            except ValueError:
                issues.append("清单不是合法 JSON：%s" % relpath)
                continue
        if actual != expected:
            issues.append("清单与生成器不一致：%s" % relpath)
    return issues


def _device():
    return load_device(SYNTH)


def evaluate_injections():
    manifest_path = os.path.join(INJECT_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    device = _device()
    verifier = crules.Verifier(device)
    rows = []
    misses = []
    for case in manifest["cases"]:
        path = os.path.join(ROOT, case["file"])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        res = verifier.check_file(os.path.basename(path), text)
        findings = res["findings"]
        hit = any(f["class"] == case["rule"] and f["line"] == case["line"] for f in findings)
        line_any = any(f["line"] == case["line"] for f in findings)
        rule_any = any(f["class"] == case["rule"] for f in findings)
        rows.append({"case": case, "hit": hit, "line_any": line_any, "rule_any": rule_any})
        if not hit:
            misses.append({
                "id": case["id"], "rule": case["rule"], "line": case["line"],
                "note": case["note"],
                "on_line": [f["class"] for f in findings if f["line"] == case["line"]],
                "rule_elsewhere": rule_any,
            })
    by_rule = []
    for rule in sorted(RECALL_TARGET):
        rule_rows = [r for r in rows if r["case"]["rule"] == rule]
        hit = sum(1 for r in rule_rows if r["hit"])
        total = len(rule_rows)
        recall = (float(hit) / total) if total else 0.0
        by_rule.append({
            "rule": rule, "cases": total, "hit": hit, "recall": recall,
            "target": RECALL_TARGET[rule], "ok": total > 0 and recall >= RECALL_TARGET[rule],
        })
    return {
        "total": len(rows), "hit": sum(1 for r in rows if r["hit"]),
        "by_rule": by_rule, "misses": misses,
    }


def evaluate_normal():
    manifest_path = os.path.join(NORMAL_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    device = _device()
    verifier = crules.Verifier(device)
    total = {"files": 0, "writes": 0, "report": 0, "undetermined": 0, "passed": 0}
    offenders = []
    for entry in manifest["files"]:
        path = os.path.join(ROOT, entry["file"])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        res = verifier.check_file(os.path.basename(path), text)
        counts = res["counts"]
        total["files"] += 1
        for key in ("writes", "report", "undetermined", "passed"):
            total[key] += counts[key]
        if counts["report"]:
            offenders.append({
                "id": entry["id"], "file": entry["file"], "report": counts["report"],
                "findings": [(f["class"], f["line"], f["message"]) for f in res["findings"]],
            })
    total["fp_files"] = len(offenders)
    total["fp_file_ratio"] = float(len(offenders)) / total["files"] if total["files"] else 0.0
    total["fp_findings_ratio"] = float(total["report"]) / total["writes"] if total["writes"] else 0.0
    total["offenders"] = offenders
    return total


def evaluate_regress():
    issues = []
    if not os.path.isdir(REGRESS_DIR):
        return issues
    device = _device()
    verifier = crules.Verifier(device)
    for name in sorted(os.listdir(REGRESS_DIR)):
        if not name.endswith(".c"):
            continue
        path = os.path.join(REGRESS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        res = verifier.check_file(name, text)
        if res["counts"]["report"]:
            issues.append({
                "file": "tests/regress/%s" % name,
                "report": res["counts"]["report"],
                "findings": [(f["class"], f["line"], f["message"]) for f in res["findings"]],
            })
    return issues


def measure_perf():
    device = _device()
    verifier = crules.Verifier(device)
    text = build_perf_case()
    best = None
    for _ in range(3):
        start = time.perf_counter()
        verifier.check_file("perf_1000.c", text)
        elapsed = time.perf_counter() - start
        if best is None or elapsed < best:
            best = elapsed
    return best


def run_book():
    inject = evaluate_injections()
    normal = evaluate_normal()
    regress = evaluate_regress()
    perf = measure_perf()
    return {"inject": inject, "normal": normal, "regress": regress, "perf": perf}


def print_book(book):
    print("== 注入集召回（每个用例 = 一处注入 + 单行 ground truth）==")
    print("%-5s %-6s %-6s %-8s %-6s %s" % ("规则", "用例", "命中", "召回", "目标", "状态"))
    for row in book["inject"]["by_rule"]:
        print("%-5s %-6d %-6d %-7.0f%% %-6.0f%% %s" % (
            row["rule"], row["cases"], row["hit"], 100.0 * row["recall"],
            100.0 * row["target"], "OK" if row["ok"] else "未达标"))
    print("合计：%d/%d 命中" % (book["inject"]["hit"], book["inject"]["total"]))
    for miss in book["inject"]["misses"][:12]:
        print("  漏报：%s（%s 第 %d 行）同行报=%s，该规则在别处命中=%s｜%s" % (
            miss["id"], miss["rule"], miss["line"], miss["on_line"],
            miss["rule_elsewhere"], miss["note"]))
    print("")
    normal = book["normal"]
    print("== 正样本集误报（预期 0 条“报”）==")
    print("文件 %d 个；写入 %d 处；报 %d 处；未判定 %d 处；通过 %d 处" % (
        normal["files"], normal["writes"], normal["report"],
        normal["undetermined"], normal["passed"]))
    print("报文件占比 %.1f%%（目标 ≤ %.0f%%）；报/写入 %.2f%%" % (
        100.0 * normal["fp_file_ratio"], 100.0 * FP_TARGET, 100.0 * normal["fp_findings_ratio"]))
    for item in normal["offenders"][:10]:
        print("  误报：%s（%d 条）" % (item["file"], item["report"]))
        for cls, line, message in item["findings"][:3]:
            print("    %s 第 %d 行：%s" % (cls, line, message))
    print("")
    print("== 回归集（tests/regress/，预期全部 0 报）==")
    if book["regress"]:
        for item in book["regress"]:
            print("  未通过：%s（报 %d 条）" % (item["file"], item["report"]))
    else:
        print("通过。")
    print("")
    print("== 性能（%d 行文件，取 3 次最好）==" % PERF_LINES)
    print("%.3f s（目标 ≤ %.1f s）" % (book["perf"], PERF_TARGET))


def book_ok(book):
    for row in book["inject"]["by_rule"]:
        if not row["ok"]:
            return False
    normal = book["normal"]
    if normal["fp_file_ratio"] > FP_TARGET:
        return False
    if normal["fp_findings_ratio"] > FP_TARGET:
        return False
    if book["regress"]:
        return False
    if book["perf"] > PERF_TARGET:
        return False
    return True


# ---------------------------------------------------------------- 文档

def render_doc(book):
    today = datetime.date.today().isoformat()
    lines = [
        "# 核验器量化基准：注入集召回 · 正样本集误报 · 性能",
        "",
        "> 自动生成：`python tools/verify_bench.py doc`（数据来自同目录下的 check 全量运行）",
        "> 日期：%s ｜ 环境：%s %s / Python %s" % (
            today, platform.system(), platform.release(), platform.python_version()),
        "",
        "## 方法",
        "",
        "- **注入集**（`tests/inject/`）：针对合成芯片 SYNTH32（`tests/fixtures/synthetic.svd`，自编，非厂商数据），",
        "  每类注入 ≥ 20 处；每处 = 一行注入 + 一条 ground truth（规则类别与行号都要命中）。用例由",
        "  `tools/verify_bench.py generate` 幂等生成，生成物入库可复核。",
        "- **正样本集**（`tests/normal/`）：≥ 50 个不含注入的文件（自写标准初始化 + 常见风格），预期 0 条“报”；",
        "  “未判定”“芯片默认”不视为误报，单独统计。",
        "- **回归集**（`tests/regress/`）：每个真实误报案例修掉后入库，每次发版必须全部通过。",
        "- **性能**：1000 行文件核验耗时（同进程 `check_file`，3 次取最好）。",
        "- 依据规格 §2.8 阈值：E01–E06/E08–E10 召回 ≥ 90%、E07 ≥ 80%、误报 ≤ 5%、1000 行 ≤ 2 s。",
        "- E11（使能后写 DMA 配置寄存器）为文本级文件级规则，不在合成芯片注入集内，另行单测覆盖。",
        "",
        "## 注入集召回",
        "",
        "| 规则 | 用例数 | 命中 | 召回 | 目标 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for row in book["inject"]["by_rule"]:
        lines.append("| %s | %d | %d | %.0f%% | %.0f%% | %s |" % (
            row["rule"], row["cases"], row["hit"], 100.0 * row["recall"],
            100.0 * row["target"], "✅" if row["ok"] else "❌"))
    lines.append("| **合计** | **%d** | **%d** | **%.1f%%** | — | %s |" % (
        book["inject"]["total"], book["inject"]["hit"],
        100.0 * book["inject"]["hit"] / book["inject"]["total"] if book["inject"]["total"] else 0.0,
        "✅" if all(r["ok"] for r in book["inject"]["by_rule"]) else "❌"))
    if book["inject"]["misses"]:
        lines.extend(["", "漏报明细：", ""])
        for miss in book["inject"]["misses"]:
            lines.append("- `%s`（%s 第 %d 行，%s）：同行报=%s，该规则在别处命中=%s" % (
                miss["id"], miss["rule"], miss["line"], miss["note"],
                miss["on_line"], miss["rule_elsewhere"]))
    normal = book["normal"]
    lines.extend([
        "",
        "## 正样本集误报",
        "",
        "| 指标 | 值 | 阈值 |",
        "|---|---|---|",
        "| 文件数 | %d | ≥ 50 |" % normal["files"],
        "| 报文件占比 | %.1f%% | ≤ %.0f%% |" % (100.0 * normal["fp_file_ratio"], 100.0 * FP_TARGET),
        "| 报/写入 | %.2f%%（%d/%d） | ≤ %.0f%% |" % (
            100.0 * normal["fp_findings_ratio"], normal["report"], normal["writes"], 100.0 * FP_TARGET),
        "| 未判定/写入 | %.1f%%（%d/%d） | 公开即可 |" % (
            100.0 * normal["undetermined"] / normal["writes"] if normal["writes"] else 0.0,
            normal["undetermined"], normal["writes"]),
        "",
        "## 回归集与性能",
        "",
        "- 回归集：%s" % ("全部通过（0 报）" if not book["regress"] else "存在未通过案例，见 check 输出"),
        "- 性能：%d 行文件 %.3f s（≤ %.1f s）" % (PERF_LINES, book["perf"], PERF_TARGET),
        "",
        "## 局限（引用上述数字时必须说明）",
        "",
        "1. 用例基于合成芯片 SYNTH32 的单份 SVD；未覆盖真实芯片的命名差异。",
        "2. 判定为词法层（与核验器同层），不代表编译器/硬件级验证。",
        "3. E05 的枚举面受夹具限制（仅 MMS 一个带枚举位域），20 条覆盖的是不同表达式写法；",
        "   E07 的使能面仅 USART2EN 一个字段，22 条覆盖不同的写入形态与顺序。",
        "4. 真实代码的误报统计见 `benchmarks/verify-dogfood.md`（本地语料，非本文件）。",
        "5. 每处注入仅判定一次，未做多次重复；查询/写读语义相关的位不在此量化。",
        "",
        "## 复现",
        "",
        "```bash",
        "python tools/verify_bench.py generate   # 重新生成用例（幂等）",
        "python tools/verify_bench.py check      # 评测（CI 同款；不达标退出码 1）",
        "python tools/verify_bench.py doc        # 重新生成本文件",
        "```",
    ])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 命令行

def cmd_generate(_args):
    written, inject_count, normal_count = write_all()
    print("已生成 %d 个文件：注入集 %d 处、正样本集 %d 个。" % (
        len(written), inject_count, normal_count))
    return 0


def cmd_check(_args):
    issues = drift_issues()
    if issues:
        for item in issues[:20]:
            print("问题：" + item)
        print("用例与生成器不一致，请先运行：python tools/verify_bench.py generate")
        return 1
    book = run_book()
    print_book(book)
    if not book_ok(book):
        print("")
        print("量化基准未达标。")
        return 1
    return 0


def cmd_doc(_args):
    issues = drift_issues()
    if issues:
        for item in issues[:20]:
            print("问题：" + item)
        print("用例与生成器不一致，请先运行：python tools/verify_bench.py generate")
        return 1
    book = run_book()
    print_book(book)
    text = render_doc(book)
    with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("")
    print("已写入 %s（达标：%s）" % (os.path.relpath(DOC, ROOT).replace("\\", "/"),
                                     "是" if book_ok(book) else "否"))
    return 0 if book_ok(book) else 1


def cmd_corpus(args):
    verify_py = os.path.join(SCRIPTS, "verify.py")
    total = {"files": 0, "writes": 0, "report": 0, "undetermined": 0, "passed": 0}
    class_counts = {}
    for directory in args.dir:
        if not os.path.isdir(directory):
            print("目录不存在：%s" % directory)
            return 1
        cmd = [sys.executable, verify_py, "check", directory, "--format", "json"]
        if args.svd:
            cmd += ["--svd", args.svd]
        if args.chip:
            cmd += ["--chip", args.chip]
        if args.no_clock_check:
            cmd += ["--no-clock-check"]
        for item in args.headers:
            cmd += ["--headers", item]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        try:
            env = json.loads(proc.stdout)
        except ValueError:
            print("无法解析 verify.py 输出（目录 %s）：%s" % (directory, proc.stdout[:400]))
            return 1
        for warning in env.get("warnings", [])[:5]:
            print("注意：%s" % warning)
        for err in env.get("errors", [])[:5]:
            print("错误：[%s] %s" % (err.get("code"), err.get("message")))
        files = [res for res in env.get("results", []) if res.get("kind") == "verify"]
        sub = {"files": len(files), "writes": 0, "report": 0, "undetermined": 0, "passed": 0}
        offenders = []
        for res in files:
            counts = res["counts"]
            for key in ("writes", "report", "undetermined", "passed"):
                sub[key] += counts[key]
            classes = sorted({f["class"] for f in res["findings"]})
            for cls in classes:
                class_counts[cls] = class_counts.get(cls, 0) + 1
            if counts["report"]:
                offenders.append((res["path"], counts["report"], classes))
        for key in total:
            total[key] += sub[key]
        ratio = "n/a"
        if sub["writes"]:
            ratio = "%.2f%%" % (100.0 * sub["report"] / sub["writes"])
        print("%s：%d 个文件、%d 处写入；报 %d（占比 %s）、未判定 %d、通过 %d" % (
            directory, sub["files"], sub["writes"], sub["report"], ratio,
            sub["undetermined"], sub["passed"]))
        for path, count, classes in sorted(offenders, key=lambda item: -item[1])[:10]:
            print("    报 %d 处 %s：%s" % (count, "/".join(classes), path))
    ratio = "n/a"
    if total["writes"]:
        ratio = "%.2f%%" % (100.0 * total["report"] / total["writes"])
    print("合计：%d 个文件、%d 处写入；报 %d（占比 %s）、未判定 %d、通过 %d" % (
        total["files"], total["writes"], total["report"], ratio,
        total["undetermined"], total["passed"]))
    if class_counts:
        print("问题类别（按文件数）：%s" % "、".join(
            "%s×%d" % (cls, count) for cls, count in sorted(class_counts.items())))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="verify_bench.py",
        description="核验器量化基准：注入集召回、正样本集误报、性能（规格 §2.8）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="生成 tests/inject/ 与 tests/normal/ 用例 + 清单")
    sub.add_parser("check", help="评测（CI 用；不达标退出码 1）")
    sub.add_parser("doc", help="评测并写入 benchmarks/verify-recall.md")
    corpus = sub.add_parser("corpus", help="真实代码语料误报统计（本地用）")
    corpus.add_argument("--dir", action="append", required=True, help="语料目录（可多次）")
    corpus.add_argument("--svd", help="SVD 路径")
    corpus.add_argument("--chip", help="芯片名（用本机 CMSIS-Pack 查找）")
    corpus.add_argument("--headers", action="append", default=[],
                        help="从头文件加载宏定义（文件或目录，可多次）")
    corpus.add_argument("--no-clock-check", action="store_true", help="关闭 E07")
    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "doc":
        return cmd_doc(args)
    if args.command == "corpus":
        return cmd_corpus(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
