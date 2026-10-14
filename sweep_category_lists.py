#!/usr/bin/python3
# Drops the names in the category lists that aren't in the Arch repositories.
# (Flatpak entries are kept.) Apps also land in categories from their AppStream data,
# so these lists only need the packages that have none.

import os
import subprocess

os.chdir("usr/share/shale-software/categories")

available = set(subprocess.run(["pacman", "-Ssq", ""], capture_output=True, text=True,
                               env={**os.environ, "LC_ALL": "C"}).stdout.split())

for file in sorted(os.listdir()):
    new = []
    with open(file) as f:
        for line in f:
            if line.startswith("flatpak:") or line == "\n" or line.rstrip() in available:
                new.append(line)
            else:
                print(f"missing {file}: {line}", end="")
    with open(file, "w") as f:
        f.write("".join(new))
