# -*- coding: utf-8 -*-
"""One try at a CODESYS visualization without the CODESYS window.

The script API offers no call that creates a visualization. This imports, in CODESYS's native
export format, the Visualization Manager and a visualization taken from the sample project that
ships with CODESYS ("RefrigeratorControl"), with its variables and texts replaced by station
variables (done before the run; the derived file is not in the repo because it is the vendor's
sample). Then it rebuilds and records the result in results/codesys_visu_attempt.txt.
"""
from __future__ import print_function
import io, os
from scriptengine import *  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
CDS = os.path.dirname(HERE)
ROOT = os.path.dirname(CDS)
BUILD = os.path.join(CDS, "build")
LOG = io.open(os.path.join(ROOT, "results", "codesys_visu_attempt.txt"), "w", encoding="utf-8")


def log(s):
    LOG.write(u"%s\n" % s)
    LOG.flush()


import shutil
shutil.copyfile(os.path.join(BUILD, "station_cds.project"), os.path.join(BUILD, "station_visu.project"))
proj = projects.open(os.path.join(BUILD, "station_visu.project"))
app = proj.active_application
for f in ["VisuManager.export", "StationVisu.export"]:
    try:
        r = app.import_native(os.path.join(BUILD, f))
        log(u"import_native %s: %s" % (f, r))
    except Exception as e:
        log(u"import_native %s FAILED: %s" % (f, e))
for c in app.get_children(False):
    log(u"object in application: %s" % c.get_name())
for cat in system.get_message_categories():
    system.clear_messages(cat)
app.rebuild()
e = w = 0
for cat in system.get_message_categories():
    for m in system.get_message_objects(cat):
        s = str(m.severity)
        if "Error" in s or "Fatal" in s:
            e += 1
        elif "Warning" in s:
            w += 1
        log(u"%s | %s%s | %s" % (s, m.prefix, m.number, m.text))
log(u"BUILD errors=%d warnings=%d" % (e, w))
proj.save()
if e == 0:
    import time
    import System
    dev = [o for o in proj.get_children(False) if getattr(o, "is_device", False)][0]
    dev.set_simulation_mode(True)
    onl = online.create_online_application(app)
    onl.login(OnlineChangeOption.Never, True)
    onl.start()
    log(u"simulation: logged in, %s" % onl.application_state)
    system.delay(4000)
    log(u"GVL_TestResult.AllPassed = %s" % onl.read_value("GVL_TestResult.AllPassed"))
    url = "http://localhost:8080/webvisu.htm"
    try:
        wc = System.Net.WebClient()
        html = wc.DownloadString(url)
        log(u"GET %s: %d characters" % (url, len(html)))
        ok = True
    except Exception as ex:
        log(u"GET %s failed: %s" % (url, ex))
        ok = False
    if ok:
        png = os.path.join(ROOT, "docs", "img", "codesys_webvisu.png")
        psi = System.Diagnostics.ProcessStartInfo(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            '--headless=new --disable-gpu --no-first-run --user-data-dir="%s" --window-size=1280,800 '
            '--virtual-time-budget=15000 --screenshot="%s" %s' % (os.path.join(BUILD, "edge_profile"), png, url))
        psi.UseShellExecute = False
        psi.CreateNoWindow = True
        pr = System.Diagnostics.Process.Start(psi)
        pr.WaitForExit(90000)
        log(u"headless Edge exit %s, screenshot exists %s" % (pr.ExitCode if pr.HasExited else "running", os.path.exists(png)))
    onl.stop()
    onl.logout()
    log(u"logged out")
proj.close()
LOG.close()
