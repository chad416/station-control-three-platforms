"""Generated drawing of the operator screen specification (docs/img/screen_spec.svg).

This is a drawing made by this script from the specification. It is NOT a screenshot of a
PanelView, WinCC or CODESYS screen. Every value on it is a placeholder (#) or an example text.

    python tools/make_screen_drawing.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 400, 240          # one screen, 800 x 480 panel drawn at half size
GAP = 24


def screen(x, y, title, body):
    s = [f'<g transform="translate({x},{y})">',
         f'<rect width="{W}" height="{H}" fill="#f4f6f8" stroke="#333" stroke-width="1.5"/>',
         f'<rect width="{W}" height="22" fill="#2b4a6f"/>',
         f'<text x="8" y="15" fill="#fff" font-size="12" font-weight="bold">{title}</text>',
         '<rect x="0" y="22" width="400" height="16" fill="#fde8e8"/>',
         '<text x="8" y="34" font-size="9" fill="#9b1c1c">Alarm banner: newest active alarm (ALMD / HMI alarm)</text>']
    s += body
    nav = ["Station", "Measurement", "Alarms", "Setup"]
    for i, n in enumerate(nav):
        s.append(f'<rect x="{8 + i * 97}" y="{H - 26}" width="90" height="20" rx="3" fill="#dfe6ee" stroke="#2b4a6f"/>')
        s.append(f'<text x="{53 + i * 97}" y="{H - 12}" font-size="10" text-anchor="middle">{n}</text>')
    s.append("</g>")
    return s


def text(x, y, t, size=10, **kw):
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<text x="{x}" y="{y}" font-size="{size}" {attrs}>{t}</text>'


def main():
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * W + 3 * GAP}" height="{2 * H + 3 * GAP + 30}" '
           'font-family="Arial, Helvetica, sans-serif">',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           text(GAP, 20, "GENERATED DRAWING of the operator screen specification - not a screenshot of any panel or runtime",
                12, font_weight="bold", fill="#b00")]
    y0 = 30 + GAP
    st = [text(10, 56, "State: 8 RejectLock", 12, font_weight="bold"),
          '<rect x="10" y="64" width="110" height="40" fill="#c62828"/>', text(65, 89, "NOK", 16, fill="#fff", text_anchor="middle", font_weight="bold"),
          text(130, 80, "Reason: 5 gate-2 force (lever unhooked?)", 10),
          text(130, 96, "Cycle time #.## s", 10),
          '<rect x="10" y="112" width="380" height="44" fill="#fff3cd" stroke="#b7791f"/>',
          text(16, 127, "REJECT LOCK: take the part out and drop it into the reject chute.", 10),
          text(16, 141, "Step 1 part removed [done]   Step 2 chute sensor saw the part [waiting]", 10),
          text(16, 153, "The lock opens only after step 2. No button opens it.", 9, fill="#555"),
          text(10, 176, "Total ####   OK ####   NOK ####   Rejects confirmed ####   NOK in a row #", 10)]
    rows = [("FpG1", "N"), ("FrG1", "N"), ("FMean", "N"), ("FHyst", "N"), ("FpG2", "N"),
            ("FPeak", "N"), ("XPeak", "mm"), ("FStep", "N"), ("XStop", "mm")]
    me = [text(10, 54, "Element      Value     Low      High     ", 10, font_family="monospace", font_weight="bold")]
    for i, (n, u) in enumerate(rows):
        me.append(text(10, 68 + i * 15, f"{n:<6} {u:<3}   ####.##   ####.##   ####.##", 10, font_family="monospace"))
        me.append(f'<circle cx="300" cy="{64 + i * 15}" r="5" fill="#2e7d32"/>')
    al = [text(10, 54, "Time      Alarm                                   State", 10, font_family="monospace", font_weight="bold")]
    for i, (n, s) in enumerate([("Fault 1: safety circuit open", "active"), ("Reject lock: part waits for chute", "active"),
                                ("Three rejects in a row: master part", "acked"), ("Fault 3: clamp time-out", "cleared")]):
        al.append(text(10, 70 + i * 15, f"hh:mm:ss  {n:<38} {s}", 10, font_family="monospace"))
    al.append('<rect x="290" y="170" width="100" height="22" rx="3" fill="#dfe6ee" stroke="#2b4a6f"/>')
    al.append(text(340, 185, "Acknowledge", 10, text_anchor="middle"))
    se = [text(10, 56, "Rig check required (3 rejects in a row): YES", 11, font_weight="bold", fill="#9b1c1c"),
          text(10, 74, "1. Put the master part in and run it.", 10),
          text(10, 88, "2. Press the acknowledge key on the station (AckFault).", 10),
          text(10, 102, "   The start stays blocked until then.", 10),
          text(10, 124, "Recipe: mode 3 (windows + return stroke)   Variant: LH", 10),
          text(10, 140, "Counters per NOK code: table 0..31 (#### each)", 10),
          text(10, 160, "Setup (password level 2): reset counters, recipe limits", 10)]
    out += screen(GAP, y0, "1 Station", st)
    out += screen(2 * GAP + W, y0, "2 Measurement (last part)", me)
    out += screen(GAP, y0 + H + GAP, "3 Alarms", al)
    out += screen(2 * GAP + W, y0 + H + GAP, "4 Setup / rig check", se)
    out.append("</svg>")
    p = ROOT / "docs" / "img" / "screen_spec.svg"
    p.write_text("\n".join(out), encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
