#!/usr/bin/env python3
"""
📚 The shelf's last step (workflow "lists"): what did not really change goes back to what it was, then the signed list of
files. Lindenhaus Player takes a list from player/lists/ only when manifest.sig is right for manifest.json and the file
matches the size and SHA-256 that manifest.json names (app: shared/.../data/Shelf.kt).

  1. Settle: a list whose content is the same as before apart from its "made" date gets its old bytes back – so a
     quiet day sends the apps nothing new. A new list that cannot be read, or is less than half the old one (a source
     that answered only in part), is not taken either: the old one stays.
  2. manifest.json: every list's SHA-256 and size (written only when a list changed – an ECDSA signature differs on
     every signing, so an unchanged manifest keeps its old signature).
  3. manifest.sig: ECDSA P-256 / SHA-256 over manifest.json's bytes, base64 (DER), with the key in the secret
     LIST_SIGNING_KEY (PEM or OpenSSH, from `ssh-keygen -t ecdsa -b 256 -m PEM`). The key is never printed; the public
     half is printed (it is public – it goes into the app).

Usage: LIST_SIGNING_KEY=… python3 sign_lists.py player/lists
"""
import base64, gzip, hashlib, json, os, subprocess, sys, datetime

NAMES = ["cream.bin", "freefilms.json", "youtube.json", "classics.json", "freetv.json", "services.json", "catnip.json"]


def old_bytes(path):
    try:
        return subprocess.run(["git", "show", "HEAD:" + path], capture_output=True, check=True).stdout
    except Exception:
        return None


def content(name, raw):
    """The list's content without its "made" date (None when it cannot be read)."""
    try:
        text = gzip.decompress(raw) if name.endswith(".bin") else raw
        doc = json.loads(text)
        if isinstance(doc, dict):
            doc.pop("made", None)
        return json.dumps(doc, sort_keys=True, ensure_ascii=False)
    except Exception:
        return None


def main(folder):
    # 1. settle
    for name in NAMES:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        new = open(path, "rb").read()
        old = old_bytes(path)
        if old is None or old == new:
            continue
        was, now = content(name, old), content(name, new)
        if now is None:
            # (a list the app could not read never reaches the apps)
            open(path, "wb").write(old)
            print(f"::warning::{name}: the new list cannot be read – kept the old one")
        elif was is not None and len(now) < len(was) // 2:
            # (a source that answered only half: the apps keep the full list)
            open(path, "wb").write(old)
            print(f"::warning::{name}: the new list is less than half the old one – kept the old one")
        elif was == now:
            open(path, "wb").write(old)
            print(f"{name}: only its date changed – kept as it was")
    # 2. the list of files
    files = {}
    for name in NAMES:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            raw = open(path, "rb").read()
            files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    man_path = os.path.join(folder, "manifest.json")
    sig_path = os.path.join(folder, "manifest.sig")
    try:
        before = json.load(open(man_path)).get("files")
    except Exception:
        before = None
    key_text = os.environ.get("LIST_SIGNING_KEY", "").strip()
    if not key_text:
        print("::error::the secret LIST_SIGNING_KEY is missing – the shelf stays unsigned and the apps take nothing (see the handbook)")
        return 1
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    data = key_text.encode()
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except Exception:
        key = serialization.load_ssh_private_key(data, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        print("::error::LIST_SIGNING_KEY is not a P-256 key (ssh-keygen -t ecdsa -b 256)")
        return 1
    point = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print("the shelf's public key (for the app, ListShelf.PUBLIC_KEY): " + base64.b64encode(point).decode())
    if before == files and os.path.exists(sig_path):
        print("no list changed – manifest and signature stay")
        return 0
    manifest = json.dumps({"version": 1, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": files},
                          indent=1, sort_keys=True).encode()
    open(man_path, "wb").write(manifest)
    sig = key.sign(manifest, ec.ECDSA(hashes.SHA256()))
    open(sig_path, "w").write(base64.b64encode(sig).decode() + "\n")
    # (the check the app makes, once here)
    key.public_key().verify(sig, manifest, ec.ECDSA(hashes.SHA256()))
    print("signed: " + ", ".join(f"{n} ({v['bytes'] // 1024} KB)" for n, v in files.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "player/lists"))
