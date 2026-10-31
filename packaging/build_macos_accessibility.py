"""Build the narrowly versioned Qt Cocoa ownership backport using the system SDK."""
import argparse
import subprocess
from pathlib import Path


def build(root: Path) -> Path:
    output = root / 'out' / 'platform-support' / '_cocoa_accessibility.dylib'
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['xcrun', 'clang', '-dynamiclib', '-fno-objc-arc', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-mmacosx-version-min=13.0', '-framework', 'AppKit',
                    str(root / 'packaging' / 'macos' / 'accessibility_fix.m'),
                    '-o', str(output)], check=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(build(Path(__file__).resolve().parent.parent))
