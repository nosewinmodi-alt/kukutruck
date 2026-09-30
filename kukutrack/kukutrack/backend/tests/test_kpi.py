import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib.util

spec = importlib.util.spec_from_file_location("kpi", Path(__file__).resolve().parents[1] / "app/services/kpi.py")
kpi = importlib.util.module_from_spec(spec); sys.modules["kpi"] = kpi; spec.loader.exec_module(kpi)
Log = kpi.Log
D = date(2026, 1, 1)


def test_layer_kpis():
    logs = [Log(D + timedelta(days=i), eggs=90, deaths=1 if i == 0 else 0, feed_kg=11.0) for i in range(10)]
    k = kpi.compute_kpis("layer", 100, logs, income=9000, expenses=6000)
    assert k["live_birds"] == 99 and k["mortality_pct"] == 1.0
    assert k["total_eggs"] == 900 and k["hen_day_pct"] == round(900 / (100 + 99 * 9) * 100, 2)
    assert k["cost_per_tray"] == 200.0 and k["profit"] == 3000 and k["fcr"] is None


def test_broiler_fcr():
    k = kpi.compute_kpis("broiler", 100, [Log(D, deaths=2, feed_kg=150, avg_weight_g=1500)])
    assert k["live_birds"] == 98 and k["fcr"] == round(150 / (98 * 1.5), 2) and k["hen_day_pct"] is None


def test_alerts():
    logs = [Log(D + timedelta(days=i), eggs=90) for i in range(7)] + [Log(D + timedelta(days=7), eggs=60, deaths=2)]
    codes = {a["code"] for a in kpi.compute_alerts("layer", 100, logs)}
    assert codes == {"egg_drop", "mortality_critical"}
    assert kpi.compute_alerts("layer", 100, []) == []
