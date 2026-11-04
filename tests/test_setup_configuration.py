"""Exercise setup planning against temporary config files only."""
from pathlib import Path
import shutil
import subprocess
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "setup_new_pc/configure_instance.ps1"
POWERSHELL = shutil.which("powershell")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="Windows PowerShell required")


def configure(tmp_path, instance="Pie64_2", ram=8192, plan=False):
    conf = tmp_path / "config.txt"
    original = ('bst.instance.Pie64.adb_port="5555"\n'
                'bst.instance.Pie64.ram="12288"\n'
                'bst.instance.Pie64_2.adb_port="5575"\n'
                'bst.instance.Pie64_2.ram="12288"\n')
    conf.write_text(original)
    output = tmp_path / "selected.txt"
    cmd = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-ConfigPath", str(conf), "-OutputPath", str(output), "-Instance", instance,
           "-TotalMemoryMB", str(ram), "-LogicalProcessors", "4"]
    if plan:
        cmd.append("-PlanOnly")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return result, conf, output, original


def test_configures_only_selected_instance_and_saves_backup(tmp_path):
    result, conf, output, _ = configure(tmp_path)
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == ["Pie64_2", "127.0.0.1:5575"]
    assert 'bst.instance.Pie64_2.ram="4096"' in conf.read_text()
    assert 'bst.instance.Pie64.ram="12288"' in conf.read_text()
    assert len(list(tmp_path.glob("*.bak"))) == 1


@pytest.mark.parametrize("instance,ram", [("Pie64_missing",8192), ("Pie64_2",4096)])
def test_invalid_selection_or_low_ram_stops_without_writing(tmp_path, instance, ram):
    result, conf, output, original = configure(tmp_path, instance, ram)
    assert result.returncode != 0
    assert conf.read_text() == original
    assert not output.exists()


def test_plan_only_preserves_config(tmp_path):
    result, conf, output, original = configure(tmp_path, ram=32768, plan=True)
    assert result.returncode == 0, result.stderr
    assert conf.read_text() == original
    assert "8192 MB" in result.stdout
    assert output.exists()
