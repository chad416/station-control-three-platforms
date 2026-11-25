"""Write the WinCC (classic, KTP700 Basic) import files for TIA Portal Openness.

    python siemens/hmi/make_hmi_xml.py      # writes siemens/hmi/xml/*.xml

The element form follows public Openness import code for classic panels (tag tables with absolute
addresses, connection, screens). There is no published schema for these files in the TIA Portal
V18 installation. Whether TIA accepts them is shown only by the import and compile record
(results/tia_hmi_build.txt).

Tags are absolute (%DB{DB}.DBW0 ...) into DB_HMI, a standard-access data block, over a
non-integrated connection. {DB} is replaced by the build script with the number TIA gave DB_HMI.
"""

from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
OUT = HERE / "xml"
CULTURE = "en-US"

# name, HMI data type, address in DB_HMI, length in bytes
TAGS = [
    ("State", "Int", "DBW0", 2), ("Verdict", "Int", "DBW2", 2), ("NokCode", "Int", "DBW4", 2),
    ("FaultCode", "Int", "DBW6", 2), ("CntConsecNok", "Int", "DBW8", 2),
    ("Locked", "Bool", "DBX10.0", 1), ("RigCheck", "Bool", "DBX10.1", 1),
    ("CallOperator", "Bool", "DBX10.2", 1), ("PartPresent", "Bool", "DBX10.3", 1),
    ("TCycle", "Real", "DBD12", 4), ("CntTotal", "DInt", "DBD16", 4), ("CntOk", "DInt", "DBD20", 4),
    ("CntNok", "DInt", "DBD24", 4), ("CntRejectConfirmed", "DInt", "DBD28", 4),
]
ELEMENTS = ["FpG1", "FrG1", "FMean", "FHyst", "FpG2", "FPeak", "XPeak", "FStep", "XStop"]
LIMITS = ["MeanLo", "MeanHi", "HystLo", "HystHi", "G2Lo", "G2Hi", "PeakFLo", "PeakFHi", "PeakXMin",
          "PeakXMax", "StepLo", "StopXLo", "StopXHi"]
for i, n in enumerate(ELEMENTS + LIMITS):
    TAGS.append((n, "Real", f"DBD{32 + 4 * i}", 4))

HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n<Document>\n  <Engineering version="V18" />\n'
        "  <DocumentInfo><Created>2026-11-25T00:00:00.0000000Z</Created><ExportSetting>WithDefaults</ExportSetting>"
        "<InstalledProducts /></DocumentInfo>\n")


class Ids:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return format(self.n - 1, "X")


def ml_text(ids, comp, text):
    t = f"<Text><body><p>{escape(text)}</p></body></Text>" if text else "<Text />"
    return (f'<MultilingualText ID="{ids()}" CompositionName="{comp}"><ObjectList>'
            f'<MultilingualTextItem ID="{ids()}" CompositionName="Items"><AttributeList><Culture>{CULTURE}</Culture>{t}'
            "</AttributeList></MultilingualTextItem></ObjectList></MultilingualText>")


def connection():
    ids = Ids()
    x = [HEAD, f'  <Hmi.Communication.Connection ID="{ids()}"><AttributeList><Name>Connection_PLC</Name>'
         "<Driver>SIMATIC S7 1500</Driver><InterfaceType>Ethernet</InterfaceType><Online>true</Online>"
         "</AttributeList><ObjectList>"]
    for i, a in enumerate(["Coordination", "DateTime", "DateTimereturn", "EventId", "FieldbusReadmailbox",
                           "FieldbusWritemailbox", "HmiIdentification", "Jobmailbox", "ProjectId",
                           "ScreenNumber", "TagManagement"]):
        x.append(f'<Hmi.Communication.AreaPointer ID="{ids()}" CompositionName="AreaPointers"><AttributeList>'
                 f"<AreaPointerType>{a}</AreaPointerType><LogicalAddress /><NameIndex>{i + 1}</NameIndex>"
                 f"</AttributeList><ObjectList>{ml_text(ids, 'Comment', '')}</ObjectList></Hmi.Communication.AreaPointer>")
    x.append("</ObjectList></Hmi.Communication.Connection>\n</Document>\n")
    return "".join(x)


def tag_table(internal=False):
    """internal=True: the same tags as HMI-internal tags, used only if no connection can be imported."""
    ids = Ids()
    x = [HEAD, f'  <Hmi.Tag.TagTable ID="{ids()}"><AttributeList><Name>Station</Name></AttributeList><ObjectList>']
    for name, typ, addr, length in TAGS:
        coding = "IEEE754" if typ == "Real" else "Binary"
        if internal:
            x.append(f'<Hmi.Tag.Tag ID="{ids()}" CompositionName="Tags"><AttributeList><Name>{name}</Name>'
                     # no DataType link: with it TIA refused the Real tags ("the Coding property is read-only")
                     f'</AttributeList><LinkList><HmiDataType TargetID="@OpenLink"><Name>{typ}</Name></HmiDataType></LinkList>'
                     f"<ObjectList>{ml_text(ids, 'Comment', '')}</ObjectList></Hmi.Tag.Tag>")
            continue
        x.append(f'<Hmi.Tag.Tag ID="{ids()}" CompositionName="Tags"><AttributeList>'
                 "<AcquisitionTriggerMode>Visible</AcquisitionTriggerMode><AddressAccessMode>Absolute</AddressAccessMode>"
                 f"<Coding>{coding}</Coding><Length>{length}</Length>"
                 f"<LogicalAddress>%DB{{DB}}.{addr}</LogicalAddress><Name>{name}</Name>"
                 "</AttributeList><LinkList>"
                 '<AcquisitionCycle TargetID="@OpenLink"><Name>1 s</Name></AcquisitionCycle>'
                 '<Connection TargetID="@OpenLink"><Name>Connection_PLC</Name></Connection>'
                 f'<DataType TargetID="@OpenLink"><Name>{typ}</Name></DataType>'
                 f'<HmiDataType TargetID="@OpenLink"><Name>{typ}</Name></HmiDataType>'
                 f"</LinkList><ObjectList>{ml_text(ids, 'Comment', '')}</ObjectList></Hmi.Tag.Tag>")
    x.append("</ObjectList></Hmi.Tag.TagTable>\n</Document>\n")
    return "".join(x)


def font(ids, size=13):
    return (f'<Hmi.Globalization.MultiLingualFont ID="{ids()}" CompositionName="Font"><ObjectList>'
            f'<Hmi.Globalization.FontItem ID="{ids()}" CompositionName="Items"><AttributeList><Culture>{CULTURE}</Culture>'
            f"<FontFamily>Tahoma</FontFamily><FontSize>{size}</FontSize><FontStyle>Regular</FontStyle>"
            "</AttributeList></Hmi.Globalization.FontItem></ObjectList></Hmi.Globalization.MultiLingualFont>")


def geom(name, left, top, w, h):
    return f"<Height>{h}</Height><Left>{left}</Left><ObjectName>{name}</ObjectName><Top>{top}</Top><Width>{w}</Width>"


def text_field(ids, name, left, top, w, h, text, size=13):
    return (f'<Hmi.Screen.TextField ID="{ids()}" CompositionName="ScreenItems"><AttributeList>'
            f"{geom(name, left, top, w, h)}<ForeColor>30, 41, 59</ForeColor></AttributeList><ObjectList>"
            f"{font(ids, size)}{ml_text(ids, 'Text', text)}</ObjectList></Hmi.Screen.TextField>")


FORMAT = {"Int": "s999999", "DInt": "s9999999999", "Real": "s99999.999", "Bool": "9"}
TYPE = {n: typ for n, typ, _a, _l in TAGS}


def io_field(ids, name, left, top, w, h, tag):
    # an IO field needs a format pattern that fits the tag (first compile: "The format pattern ... is invalid")
    return (f'<Hmi.Screen.IOField ID="{ids()}" CompositionName="ScreenItems"><AttributeList>'
            f"<FormatPattern>{FORMAT[TYPE[tag]]}</FormatPattern>{geom(name, left, top, w, h)}<Mode>Output</Mode></AttributeList><ObjectList>{font(ids)}"
            f'<Hmi.Screen.Property ID="{ids()}" CompositionName="Properties"><AttributeList><Name>ProcessValue</Name></AttributeList>'
            f'<ObjectList><Hmi.Dynamic.TagConnectionDynamic ID="{ids()}" CompositionName="Dynamic"><AttributeList><Indirect>false</Indirect>'
            f'</AttributeList><LinkList><Tag TargetID="@OpenLink"><Name>{tag}</Name></Tag></LinkList>'
            "</Hmi.Dynamic.TagConnectionDynamic></ObjectList></Hmi.Screen.Property></ObjectList></Hmi.Screen.IOField>")


def button(ids, name, left, top, w, h, text, screen=None):
    ev = ""
    if screen:
        ev = (f'<Hmi.Event.Event ID="{ids()}" CompositionName="Events"><AttributeList><Name>Click</Name></AttributeList><ObjectList>'
              f'<Hmi.Event.FunctionListEventHandler ID="{ids()}" CompositionName="EventHandler"><ObjectList>'
              f'<Hmi.Event.FunctionListEntry ID="{ids()}" CompositionName="FunctionListEntries"><AttributeList>'
              "<Name>ActivateScreen</Name><Type>SystemFunction</Type></AttributeList><ObjectList>"
              f'<Hmi.Event.FunctionListEntryParameter ID="{ids()}" CompositionName="Parameters"><AttributeList><Name>Screen name</Name>'
              f'</AttributeList><LinkList><Value TargetID="@OpenLink"><Name>{screen}</Name></Value></LinkList>'
              "</Hmi.Event.FunctionListEntryParameter></ObjectList></Hmi.Event.FunctionListEntry></ObjectList>"
              "</Hmi.Event.FunctionListEventHandler></ObjectList></Hmi.Event.Event>")
    return (f'<Hmi.Screen.Button ID="{ids()}" CompositionName="ScreenItems"><AttributeList>'
            f"{geom(name, left, top, w, h)}</AttributeList><ObjectList>{font(ids)}"
            f"{ml_text(ids, 'TextOff', text)}{ml_text(ids, 'TextOn', text)}{ev}</ObjectList></Hmi.Screen.Button>")


SCREENS = ["Station", "Measurement", "Alarms", "Setup"]


def screen(name, number, items, nav=True):
    ids = Ids()
    body = items(ids)
    if nav:
        for i, s in enumerate(SCREENS):
            body.append(button(ids, "Nav" + s, 8 + i * 196, 424, 188, 48, s, s))
    return (HEAD + f'  <Hmi.Screen.Screen ID="{ids()}"><AttributeList><ActiveLayer>0</ActiveLayer>'
            f"<Height>480</Height><Name>{name}</Name><Number>{number}</Number><Visible>true</Visible><Width>800</Width>"
            f'</AttributeList><ObjectList>{ml_text(ids, "HelpText", "")}'
            f'<Hmi.Screen.ScreenLayer ID="{ids()}" CompositionName="Layers"><AttributeList><Index>0</Index><Name />'
            f"<VisibleES>true</VisibleES></AttributeList><ObjectList>{''.join(body)}</ObjectList></Hmi.Screen.ScreenLayer>"
            "</ObjectList></Hmi.Screen.Screen>\n</Document>\n")


def station(ids):
    rows = [("State", "State (0 Idle ... 8 RejectLock ... 10 Home)"), ("Verdict", "Verdict (1 OK, 2 NOK)"),
            ("NokCode", "NOK reason code"), ("FaultCode", "Fault code"), ("TCycle", "Cycle time, s"),
            ("CntTotal", "Parts total"), ("CntOk", "OK"), ("CntNok", "NOK"),
            ("CntRejectConfirmed", "Rejects confirmed in the chute"), ("CntConsecNok", "NOK in a row"),
            ("Locked", "Reject lock (1 = remove part, drop it into the chute)"), ("PartPresent", "Part in fixture")]
    out = [text_field(ids, "Title", 8, 8, 600, 28, "Force-travel test station", 16)]
    for i, (tag, label) in enumerate(rows):
        out.append(text_field(ids, "L" + tag, 8, 44 + i * 31, 420, 26, label))
        out.append(io_field(ids, "V" + tag, 440, 44 + i * 31, 140, 26, tag))
    return out


def measurement(ids):
    out = [text_field(ids, "Title", 8, 8, 600, 28, "Curve elements of the last part and their limits", 16)]
    lim = {"FMean": ("MeanLo", "MeanHi"), "FHyst": ("HystLo", "HystHi"), "FpG2": ("G2Lo", "G2Hi"),
           "FPeak": ("PeakFLo", "PeakFHi"), "XPeak": ("PeakXMin", "PeakXMax"), "FStep": ("StepLo", None),
           "XStop": ("StopXLo", "StopXHi")}
    for i, e in enumerate(ELEMENTS):
        y = 44 + i * 40
        out.append(text_field(ids, "L" + e, 8, y, 120, 30, e))
        if e in lim and lim[e][0]:
            out.append(io_field(ids, "Lo" + e, 140, y, 140, 30, lim[e][0]))
        out.append(io_field(ids, "V" + e, 300, y, 140, 30, e))
        if e in lim and lim[e][1]:
            out.append(io_field(ids, "Hi" + e, 460, y, 140, 30, lim[e][1]))
    return out


def alarms(ids):
    return [text_field(ids, "Title", 8, 8, 600, 28, "Alarms", 16),
            text_field(ids, "Note", 8, 50, 780, 120,
                       "Station alarms are Program_Alarm instances in the CPU (FB_StationAlarms): safety circuit open, "
                       "drive not ready, clamp time-out, tare failed, reject waiting, rig check. Fault code now:"),
            io_field(ids, "VFaultCode", 8, 180, 140, 30, "FaultCode"),
            text_field(ids, "LCall", 8, 220, 420, 30, "Operator called"),
            io_field(ids, "VCall", 440, 220, 140, 30, "CallOperator")]


def setup(ids):
    return [text_field(ids, "Title", 8, 8, 600, 28, "Setup / rig check", 16),
            text_field(ids, "LRig", 8, 50, 420, 30, "Rig check required (3 rejects in a row)"),
            io_field(ids, "VRig", 440, 50, 140, 30, "RigCheck"),
            text_field(ids, "Step1", 8, 100, 780, 30, "1. Put the master part in and run it."),
            text_field(ids, "Step2", 8, 136, 780, 30, "2. Press the acknowledge key at the station. The start stays blocked until then.")]


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "connection.xml").write_text(connection(), encoding="utf-8")
    (OUT / "tags_Station.xml").write_text(tag_table(), encoding="utf-8")
    (OUT / "tags_Station_internal.xml").write_text(tag_table(internal=True), encoding="utf-8")
    for i, (n, f) in enumerate(zip(SCREENS, [station, measurement, alarms, setup])):
        (OUT / f"screen_{n}.xml").write_text(screen(n, i + 1, f), encoding="utf-8")
        # the same screen without the navigation buttons, imported only if the first form is refused
        (OUT / f"screen_{n}_nonav.xml").write_text(screen(n, i + 1, f, nav=False), encoding="utf-8")
    print("written", sorted(p.name for p in OUT.glob("*.xml")))


if __name__ == "__main__":
    main()
