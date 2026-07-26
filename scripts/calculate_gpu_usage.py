"""Calculate average GPU utilization from an nvidia-smi dmon log."""

from pathlib import Path
import sys


log_path = Path(sys.argv[1])
sm_values: list[int] = []

for line in log_path.read_text(encoding="utf-8").splitlines():
    columns = line.split()

    # With `nvidia-smi dmon -s u`, every data line starts with:
    # GPU_ID  SM_PERCENT  ...
    if not columns or columns[0].startswith("#"):
        continue

    try:
        sm_values.append(int(columns[1]))
    except (IndexError, ValueError):
        continue


if not sm_values:
    print(f"No GPU utilization samples found in {log_path}")
    raise SystemExit(1)


active_values = [value for value in sm_values if value > 0]

average = sum(sm_values) / len(sm_values)
active_average = (
    sum(active_values) / len(active_values)
    if active_values
    else 0
)
idle_percentage = (
    (len(sm_values) - len(active_values))
    / len(sm_values)
    * 100
)

print(f"Samples: {len(sm_values)}")
print(f"Average SM utilization: {average:.1f}%")
print(f"Average active SM utilization: {active_average:.1f}%")
print(f"Idle samples: {idle_percentage:.1f}%")
