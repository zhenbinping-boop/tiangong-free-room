#!/usr/bin/env python3
"""生成 Digital Asset Links 文件（TWA 去掉地址栏的验证依据）。

用法：
    python tools/make_assetlinks.py \
        --package app.tiangong.freeroom \
        --sha256 0b62cc... \
        [--sha256 <另一个指纹>] \
        [--out web/.well-known/assetlinks.json]

指纹来源：keytool -list -v -keystore android/release.keystore -alias tiangong-rooms
（输出里的 SHA256: 去掉冒号）

为什么做成脚本：指纹一旦换签名就会变，手写容易漏位或带冒号，
而验证失败在 TWA 里没有报错，只表现为顶部悄悄多出一条地址栏。
"""

import argparse
import json
import os
import sys

REQ_RELATION = [
    'delegate_permission/common.handle_all_urls',
    'delegate_permission/common.get_login_creds',
]


def build(package, fingerprints):
    return [{
        'relation': REQ_RELATION,
        'target': {
            'namespace': 'android_app',
            'package_name': package,
            'sha256_cert_fingerprints': list(fingerprints),
        },
    }]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', default='app.tiangong.freeroom')
    ap.add_argument('--sha256', action='append', dest='fingerprints', required=True,
                    help='APK 签名证书的 SHA-256 指纹（64 位十六进制，可重复传入多个）')
    ap.add_argument('--out', default=os.path.join('web', '.well-known', 'assetlinks.json'))
    args = ap.parse_args()

    clean = []
    for fp in args.fingerprints:
        f = fp.strip().replace(':', '').lower()
        if len(f) != 64 or any(c not in '0123456789abcdef' for c in f):
            sys.exit(f'指纹不是 64 位十六进制：{fp}')
        clean.append(f)

    doc = build(args.package, clean)
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f'已写入 {args.out}')
    print(json.dumps(doc, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
