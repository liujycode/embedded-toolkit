"""embedded-timing-calc 计算器回归：每个计算器至少一条期望数值断言。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "embedded-timing-calc" / "scripts" / "timing.py"


def _load_timing():
    spec = importlib.util.spec_from_file_location("etk_timing", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


timing = _load_timing()


def _text(result):
    ok, lines = result
    return ok, "\n".join(lines)


def _expect(result):
    ok, text = _text(result)
    return ok, text


def test_uart_numeric():
    ok, text = _expect(timing.calc_uart(72e6, 115200))
    assert ok is True
    assert "BRR（分频值）= 39" in text
    assert "实际波特率 = 115384.62" in text
    assert "误差 = 0.160%" in text


def test_timer_numeric():
    ok, text = _expect(timing.calc_timer(72e6, psc=71, arr=999))
    assert ok is True
    assert "输出频率 = 1000.0000 Hz" in text
    ok, text = _expect(timing.calc_timer(72e6, freq=1000))
    assert ok is True
    assert "实际=1000.0000 Hz" in text


def test_i2c_rp_fast_200pf_and_hs_unsupported():
    ok, text = _expect(timing.calc_i2c_rp("fast", 200))
    assert ok is True
    assert "Rp_max = tr/(k×Cb) = 300ns/(0.8473×200pF) = 1.77 kΩ" in text
    assert "推荐标准阻值：1k、1.5k" in text
    assert "4.7k" not in text
    # std/fm+ 与 fast 同用 0.8473，hs 是电流源上拉、必须显式拒绝
    ok, text = _expect(timing.calc_i2c_rp("fmplus", 100))
    assert ok is True
    assert "0.8473×100pF" in text
    with pytest.raises(timing.CalcError) as exc:
        timing.calc_i2c_rp("hs", 50)
    assert exc.value.code == "E_UNSUPPORTED"
    assert "电流源" in str(exc.value)


def test_i2c_time_numeric():
    ok, text = _expect(timing.calc_i2c_time("std", 6))
    assert ok is True
    assert "传输耗时 ≈ 650.00 µs" in text


def test_can_10m_500k_87_5_uses_85_percent():
    ok, text = _expect(timing.calc_can(10e6, 500e3, 87.5, "bxcan"))
    assert ok is True
    assert "TQ 总数 = 20（BRP=1）" in text
    assert "Prop+Ph1=16、Ph2=3" in text
    assert "采样点 = 85.0%" in text


def test_can_bxcan_50m_2m_rejects_seg1_19_fdcan_accepts():
    ok, text = _expect(timing.calc_can(50e6, 2e6, 80.0, "bxcan"))
    assert ok is False
    assert "Prop+Ph1=16、Ph2=8" in text
    assert "采样点 = 68.0%" in text
    assert "PASS" not in text
    ok, text = _expect(timing.calc_can(50e6, 2e6, 80.0, "fdcan"))
    assert ok is True
    assert "Prop+Ph1=19、Ph2=5" in text
    assert "采样点 = 80.0%" in text


def test_can_42m_500k_enumeration():
    ok, text = _expect(timing.calc_can(42e6, 500e3, 87.5, "bxcan"))
    assert ok is True
    assert "TQ 总数 = 14（BRP=6）" in text
    assert "采样点 = 85.7%" in text


def test_adc_rad_numeric_and_radc():
    ok, text = _expect(timing.calc_adc_rad(47, 42e6, 12, 8.0))
    assert ok is True
    assert "Rsrc_max = 14.4 kΩ" in text
    assert "未扣 Radc" in text
    ok, text = _expect(timing.calc_adc_rad(47, 42e6, 12, 8.0, 1000.0))
    assert ok is True
    assert "已扣片内 Radc = 1000 Ω" in text
    assert "14.4 kΩ − 1.0 kΩ = 13.4 kΩ" in text


def test_rc_numeric():
    ok, text = _expect(timing.calc_rc(1000, 100e-9))
    assert ok is True
    assert "截止频率 fc = 1591.55 Hz" in text


def test_spi_numeric():
    ok, text = _expect(timing.calc_spi(84e6, 8))
    assert ok is True
    assert "SCK = 1.05e+07 Hz" in text


def test_nyquist_numeric():
    ok, text = _expect(timing.calc_nyquist(1000, 100))
    assert ok is True
    assert "fs/fbw = 10.00 倍" in text


def test_deadtime_numeric():
    ok, text = _expect(timing.calc_deadtime(20e3, 500e-9))
    assert ok is True
    assert "死区占比 = 1.00%" in text


def test_fpga_uart_numeric():
    ok, text = _expect(timing.calc_fpga_uart(50e6, 115200))
    assert ok is True
    assert "整数分频 N = 434" in text
    assert "实际波特率 = 115207.37" in text


def test_fpga_slack_numeric():
    ok, text = _expect(timing.calc_fpga_slack(10, 2.5, 3.2, 3.1, 0.8))
    assert ok is True
    assert "总延时 = Tco+Tlogic+Troute+Tsu = 9.60 ns" in text
    assert "0.40 ns" in text
    assert "理论 Fmax = 104.2 MHz" in text


def test_fpga_pwm_numeric():
    ok, text = _expect(timing.calc_fpga_pwm(50e6, 20e3))
    assert ok is True
    assert "每 PWM 周期计数 = 2500.0" in text
    assert "理论位深 = 11.29 位" in text


def test_wdg_numeric():
    ok, text = _expect(timing.calc_wdg(40000, 256, 625))
    assert ok is True
    assert "超时时间 = 4.000 s" in text


def test_pll_numeric():
    ok, text = _expect(timing.calc_pll(8e6, 4, 80, 2))
    assert ok is True
    assert "VCO = Clkin/M×N = 8/4×80 = 160.000 MHz" in text
    assert "输出 = VCO/P = 80.000 MHz" in text


def test_divider_current_mode_numeric():
    ok, text = _expect(timing.calc_divider(12.0, 3.3, 100.0))
    assert ok is True
    assert "R_total = Vin/I = 120.0 kΩ" in text
    assert "R1 = (Vin-Vout)/I = 87.0 kΩ" in text
    assert "R2 = Vout/I = 33.0 kΩ" in text
    assert "R1 = 91.0 kΩ、R2 = 33.0 kΩ" in text
    assert "Vout' = 3.1935 V（误差 3.23%）" in text


def test_divider_default_r2_10k_numeric():
    ok, text = _expect(timing.calc_divider(12.0, 3.3))
    assert ok is True
    assert "R1 = R2×(Vin-Vout)/Vout = 26363.6 Ω" in text
    assert "27.0 kΩ" in text
    assert "Vout' = 3.2432 V（误差 1.72%）" in text


def test_ntc_numeric():
    ok, text = _expect(timing.calc_ntc(10000, 3950, 50))
    assert ok is True
    assert "50°C 时 NTC 阻值 = 3588.2 Ω" in text


def test_rc_settle_numeric():
    ok, text = _expect(timing.calc_rc_settle(10000, 100e-9, 10))
    assert ok is True
    assert "t ≈ 6.93 τ" in text
    assert "0.00693 s" in text


def test_ppm_numeric():
    ok, text = _expect(timing.calc_ppm(8e6, 20))
    assert ok is True
    assert "漂移 = ±160 Hz" in text
    assert "±0.0020%" in text


def test_fpga_i2c_numeric():
    ok, text = _expect(timing.calc_fpga_i2c(50, 250))
    assert ok is True
    assert "= 1e+05 Hz" in text
    assert "半位时间 = 5.00 µs" in text


def test_fpga_debounce_numeric():
    ok, text = _expect(timing.calc_fpga_debounce(50e6, 20))
    assert ok is True
    assert "消抖窗口 20 ms = 1e+06 个时钟周期" in text
    assert "20 位计数器" in text


def test_fpga_cdc_numeric_rule_count():
    ok, text = _expect(timing.calc_fpga_cdc())
    assert ok is True
    assert "2 级触发器" in text
    assert "MTBF" in text


def test_fpga_fifo_numeric():
    ok, text = _expect(timing.calc_fpga_uart_fifo(115200, 230400, 64, 128))
    assert ok is True
    assert "写入速率 = 11520 字节/s" in text
    assert "排空需 2.78 ms" in text
    ok, text = _expect(timing.calc_fpga_uart_fifo(230400, 115200, 64, 128))
    assert ok is False
    assert "稳态积压 11520 字节/秒" in text


def test_esp32_clk_numeric():
    ok, text = _expect(timing.calc_esp32_clk(target=10e6))
    assert ok is True
    assert "分频系数 = 80M/target = 8.0000" in text
    assert "分频 8，实际 1e+07 Hz" in text


def test_rp2040_uart_numeric_and_fbrd_carry():
    ok, text = _expect(timing.calc_rp2040_uart(125e6, 115200))
    assert ok is True
    assert "IBRD=67、FBRD=52、实际分频 67.8125" in text
    assert "实际波特率 = 115207.37" in text
    ok, text = _expect(timing.calc_rp2040_uart(31.92e6, 1e6))
    assert ok is True
    assert "IBRD=2、FBRD=0、实际分频 2.0000" in text
    assert "997500.00" in text


def test_pwm_dim_numeric():
    ok, text = _expect(timing.calc_pwm_dim(72e6, 1000))
    assert ok is True
    assert "每周期计数 = 72000" in text
    assert "分辨率 = 16.14 位" in text


def test_ws2812_high_low_and_uncovered():
    ok, text = _expect(timing.calc_ws2812(300, 800))
    assert ok is True
    assert "T0H = 300 ns" in text
    assert "T1H = 800 ns" in text
    assert "未覆盖" in text
    ok, text = _expect(timing.calc_ws2812(300, 800, 850, 450))
    assert ok is True
    assert "T0L = 850 ns" in text
    assert "T1L = 450 ns" in text
    ok, text = _expect(timing.calc_ws2812(300, 800, 300, 450))
    assert ok is False
    assert "T0L = 300 ns" in text


def test_servo_numeric():
    ok, text = _expect(timing.calc_servo(pulse_us=1500))
    assert ok is True
    assert "角度 90.0°" in text
    ok, text = _expect(timing.calc_servo(angle=180))
    assert ok is True
    assert "脉宽 2500 µs" in text


def test_stepper_numeric():
    ok, text = _expect(timing.calc_stepper(pulse_us=5, rpm=60, pclk=1e6))
    assert ok is True
    assert "每转步数 = 360/1.8 × 16 细分 = 3200 步" in text
    assert "STEP 频率 = 3200 Hz" in text


def test_serial_baud_numeric():
    ok, text = _expect(timing.calc_serial_baud("debug"))
    assert ok is True
    assert "115200 bps" in text
    with pytest.raises(timing.CalcError):
        timing.calc_serial_baud("nope")


def test_rtc_drift_negative_ppm():
    ok, text = _expect(timing.calc_rtc_drift(-20, 1))
    assert ok is True
    assert "-20 ppm → 每日误差 ±1.73 s（慢）" in text
    assert "1 天累计误差 ±1.73 s" in text
    with pytest.raises(timing.CalcError):
        timing.calc_rtc_drift(20, 0)


def test_usb_clk_720m_and_66m():
    ok, text = _expect(timing.calc_usb_clk(720e6, ""))
    assert ok is True
    assert "/ 15 = 48 MHz" in text
    assert "整数可分 ≠ RCC 实际支持该分频" in text
    ok, text = _expect(timing.calc_usb_clk(66e6, ""))
    assert ok is False
    assert "最近 /2 = 33.00 MHz" in text


def test_battery_numeric():
    ok, text = _expect(timing.calc_battery(1000, 100))
    assert ok is True
    assert "= 8.0 小时" in text
    ok, text = _expect(timing.calc_battery(1000, 100, derate=False))
    assert ok is True
    assert "= 10.0 小时" in text


def test_modbus_silence_numeric():
    ok, text = _expect(timing.calc_modbus_silence(9600))
    assert ok is True
    assert "= 4.010 ms" in text


def test_flash_wear_page_record_and_conservative():
    ok, text = _expect(timing.calc_flash_wear(4096, 1000, 10000, 1, 64))
    assert ok is False
    assert "8760000 × 64/4096 = 136875 次/年" in text
    assert "寿命 0.0731 年" in text
    ok, text = _expect(timing.calc_flash_wear(64, 1000, 10000, 1, 64))
    assert ok is False
    assert "8760000 × 64/64 = 8760000 次/年" in text
    assert "寿命 0.00114 年" in text
    ok, text = _expect(timing.calc_flash_wear(None, 1000, 10000, 1))
    assert ok is False
    assert "未给 --record" in text
    assert "保守口径" in text
    with pytest.raises(timing.CalcError):
        timing.calc_flash_wear(None, 1000, 10000, 1, 64)


def test_spi_time_numeric():
    ok, text = _expect(timing.calc_spi_time(10, 1e6))
    assert ok is True
    assert "传输 80.0 µs" in text
    assert "实际 82.0 µs" in text


def test_sensor_lsb_bipolar_and_unipolar():
    ok, text = _expect(timing.calc_sensor_lsb(8192, 2.0, 16))
    assert ok is True
    assert "LSB = 2×FSR/2^nbits = 4 / 2^16 = 6.10352e-05" in text
    assert "raw 8192 → 物理量 0.5" in text
    ok, text = _expect(timing.calc_sensor_lsb(8192, 2.0, 16, unipolar=True))
    assert ok is True
    assert "raw 8192 → 物理量 0.25" in text


def test_cli_wires_new_options_and_list_count(capsys):
    assert timing.main(["can-bit", "--clk", "50000000", "--baud", "2000000",
                        "--sp", "80", "--family", "fdcan"]) == 0
    assert "Prop+Ph1=19" in capsys.readouterr().out
    assert timing.main(["adc-rad", "--ts", "47", "--fadc", "42000000",
                        "--radc", "1000"]) == 0
    assert "13.4 kΩ" in capsys.readouterr().out
    assert timing.main(["divider", "--vin", "12", "--vout", "3.3", "--iua", "100"]) == 0
    assert "R2 = Vout/I = 33.0 kΩ" in capsys.readouterr().out
    assert timing.main(["flash-wear", "--page", "4096", "--record", "64",
                        "--freq", "1000", "--pages", "1"]) == 1
    assert "136875 次/年" in capsys.readouterr().out
    assert timing.main(["sensor-lsb", "--raw", "8192", "--fsr", "2",
                        "--nbits", "16", "--unipolar"]) == 0
    assert "物理量 0.25" in capsys.readouterr().out
    assert timing.main(["ws2812", "--t0h", "300", "--t1h", "800",
                        "--t0l", "850", "--t1l", "450"]) == 0
    assert "T0L = 850 ns" in capsys.readouterr().out
    assert timing.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "共 37 个计算器" in out
    assert "sensor-lsb" in out
