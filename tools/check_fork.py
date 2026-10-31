"""Run portable core/Qt regression checks in isolated processes (no real desktop input).

Use --include-long to include the two extensive network simulation suites.
Native Windows tests and physical X11/Wayland sessions remain separate checks.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LONG = {'test_crossing_e2e', 'test_profiles_e2e'}
QT_TESTS = ('test_audio_ui', 'test_installer_maintenance', 'test_settings_behaviour', 'test_app_config', 'test_settings_migration',
            'test_linux_start', 'test_linux_permissions', 'test_inject_x11',
            'test_inject_portal', 'test_capture_x11', 'test_capture_portal',
            'test_sender_motion_flow', 'test_same_os_keys', 'test_linux_desktop',
            'test_portal', 'test_pages_win', 'test_i18n_pages', 'test_parity',
            'test_windows_tool_encoding', 'test_horizontal_scroll')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-long', action='store_true')
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--output', type=Path, default=ROOT / 'validation')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    modules = ['core.tests.' + p.stem for p in sorted((ROOT / 'core/tests').glob('test_*.py'))
               if args.include_long or p.stem not in LONG]
    modules += ['win_app.tests.' + name for name in QT_TESTS]
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
               PYTHONPATH=os.pathsep.join(map(str, [ROOT/'win_app/tests', ROOT/'win_app', ROOT])))

    def run(module):
        started = time.monotonic()
        try:
            result = subprocess.run([sys.executable, '-m', 'unittest', module],
                                    cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=args.timeout)
            output = result.stdout.decode(errors='replace')
            status = 'pass' if result.returncode == 0 else 'fail'
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or b'').decode(errors='replace')
            status = 'timeout'
        (args.output / (module + '.log')).write_text(output, encoding='utf-8')
        counts = re.findall(r'Ran (\d+) tests?', output)
        skips = re.findall(r'skipped=(\d+)', output)
        record = dict(module=module, status=status, tests=int(counts[-1]) if counts else None,
                      skipped=int(skips[-1]) if skips else 0,
                      seconds=round(time.monotonic()-started, 2))
        print(json.dumps(record), flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        records = list(pool.map(run, modules))
    report = dict(results=records, excluded_long=[] if args.include_long else sorted(LONG))
    (args.output/'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return int(any(r['status'] != 'pass' for r in records))


if __name__ == '__main__':
    raise SystemExit(main())
