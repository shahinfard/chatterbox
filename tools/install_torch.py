#!/usr/bin/env python3
"""
Detect GPU/CUDA on the host (via nvidia-smi) and install a matching PyTorch wheel
into the currently-activated Python environment (expects to run inside the repo .venv).

Usage:
  python tools/install_torch.py [--cpu] [--yes]

Options:
  --cpu    Install CPU-only build
  --yes    Do not prompt for confirmation

This script does NOT attempt to pick a CUDA version for you if detection is ambiguous;
it prints the recommended pip command and will prompt before running it.
"""

import argparse
import re
import shutil
import subprocess
import sys


def run(cmd):
    print("\n>>>", " ".join(cmd))
    subprocess.check_call(cmd)


def detect_cuda_version():
    nvidia = shutil.which("nvidia-smi")
    # Try the structured query which is preferred
    if nvidia:
        try:
            out = subprocess.check_output([nvidia, "--query-gpu=cuda_version", "--format=csv,noheader"], encoding="utf-8", stderr=subprocess.STDOUT)
            ver = out.strip().splitlines()[0].strip()
            if ver:
                return ver
        except Exception:
            pass

    # Fallback: run plain `nvidia-smi` and parse the human-readable output for "CUDA Version: X"
    try:
        # On Windows, shutil.which might fail due to PATH differences; try invoking without full path
        out = subprocess.check_output([nvidia or "nvidia-smi"], shell=False, encoding="utf-8", stderr=subprocess.STDOUT)
    except Exception:
        try:
            out = subprocess.check_output("nvidia-smi", shell=True, encoding="utf-8", stderr=subprocess.STDOUT)
        except Exception:
            return None

    # Look for lines like: "| NVIDIA-SMI 531.29                 Driver Version: 531.29         CUDA Version: 12.1     |"
    m = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", out)
    if m:
        return m.group(1)
    return None


def map_cuda_to_tag(cuda_ver: str):
    if not cuda_ver:
        return None
    # Normalize to major.minor (e.g. '12.1')
    parts = cuda_ver.strip().split('.')
    if len(parts) >= 2:
        mj = parts[0]
        mn = parts[1]
        key = f"{mj}.{mn}"
    else:
        key = cuda_ver

    mapping = {
        "13.1": "cu131",
        "13.0": "cu130",
        "12.1": "cu121",
        "12.0": "cu120",
        "11.8": "cu118",
        "11.7": "cu117",
        "11.6": "cu116",
        "11.3": "cu113",
        "11.1": "cu111",
    }
    return mapping.get(key)


def build_pip_command(tag: str, cpu=False):
    pkgs = ["torch", "torchvision", "torchaudio"]
    if cpu:
        index = "https://download.pytorch.org/whl/cpu"
    else:
        index = f"https://download.pytorch.org/whl/{tag}"
    cmd = [sys.executable, "-m", "pip", "install", "-U"] + pkgs + ["--index-url", index]
    return cmd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cpu", action="store_true", help="Install CPU-only PyTorch")
    p.add_argument("--yes", action="store_true", help="Do not prompt, just run the install")
    args = p.parse_args()

    if args.cpu:
        print("CPU-only install requested.")
        cmd = build_pip_command(tag=None, cpu=True)
        print("About to run the CPU install command:")
        print(" ".join(cmd))
        if args.yes or input("Proceed? [y/N]: ").lower().startswith("y"):
            run(cmd)
        else:
            print("Aborting.")
        return

    cuda_ver = detect_cuda_version()
    if cuda_ver:
        print(f"Detected CUDA version from nvidia-smi: {cuda_ver}")
    else:
        print("No `nvidia-smi` found or CUDA version not detected.")

    tag = map_cuda_to_tag(cuda_ver)
    if tag:
        print(f"Recommended PyTorch wheel tag: {tag}")
        cmd = build_pip_command(tag=tag)
        print("About to run the following pip command to install a matching PyTorch build:")
        print(" ".join(cmd))
        if args.yes or input("Proceed with this install? [y/N]: ").lower().startswith("y"):
            try:
                run(cmd)
                print("\nPyTorch install finished.")
            except subprocess.CalledProcessError:
                print("\nInstallation failed. You can try installing a different wheel manually.")
        else:
            print("Aborted by user.")
    else:
        print("Could not map detected CUDA version to a known PyTorch wheel tag.")
        print("Options:")
        print(" - Run with --cpu to install a CPU-only build:")
        print("     python tools/install_torch.py --cpu")
        print(" - Or manually choose an index-url from https://download.pytorch.org/whl/ (e.g. cu121, cu118)")
        print("Example manual commands:")
        print(" - CUDA 13.0 (newer RTX 4090/5090 drivers report CUDA 13.0):")
        print(f"    {sys.executable} -m pip install -U torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130")
        print(" - CUDA 12.1 (common for many setups):")
        print(f"    {sys.executable} -m pip install -U torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        print("\nIf you're unsure which CUDA tag to pick, visit https://pytorch.org/get-started/locally/ for guidance.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
