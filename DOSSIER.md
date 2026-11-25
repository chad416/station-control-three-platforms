# Porting one station's control between PLC platforms

**Short systems-engineering dossier, revision 1.1 (25 Nov 2026).** Simulation only: no hardware, no measured data. Every number comes from a file in `results/` or from the records of the earlier door-handle project, and says which. The layout follows the spine of Wasson, *System Engineering Analysis, Design, and Development* (need, operations, requirements, architecture, verification, limits); the book was not re-read for this project.

**Central question.** What has to change, and what must stay identical, when the control of one station moves from Siemens SCL to a CODESYS-based controller and to Allen-Bradley Logix, and how is it shown that the port behaves the same?

**Short answer.** The station logic stays the same. The port is forced at the edges: names the other compiler reserves, access into instance data (CODESYS refuses it, Logix allows only atomic Input and Output parameters and hides local tags), array bounds, global data and start values, and how the screen reaches the data. The proof is the same self-checking bench with the same expected values. The thing that decides equivalence on a real machine is the time base, and the bench cannot check it.

## 1. Need

A machine builder writes the station once and must deliver it on the controller the end customer has standardised on. The customer needs the same verdicts, the same reject lock and the same counters, whatever the controller. The builder needs to know what work a port is, and how to prove it without retesting every part on the machine.

## 2. Operational concept of the proof

The bench runs inside the controller, needs no input, and finishes by itself:

1. Replay: 10 recorded force-travel curves go sample by sample into `FB_CurveEval` in 14 cases (four evaluation modes). Verdict, NOK code, nine curve elements and two envelope counts are compared with the values of the reference evaluation. Tolerance 0.001 N or mm.
2. Station: `FB_HandleStation` runs against a plant stand-in in 6 cases: good part, wrong hand (axis and clamp must not move), reject lock against an early chute signal and a new part, unhooked latch lever, third reject in a row (master part asked for, start blocked), acknowledge and a good part.
3. The result list holds `Done`, `AllPassed`, per-case pass, failed check and NOK code, the largest element difference and the number of calls.

## 3. Requirements on the port

| Id | Requirement | Result |
|---|---|---|
| P1 | Same verdict and NOK code in every bench case | CODESYS 20 of 20 executed (`results/codesys_bench.json`); Logix 20 of 20 in the subset interpreter only (`results/logix_interpreter_bench.json`) |
| P2 | Curve elements within 0.001 of the expected values | CODESYS largest difference 9.536743E-07; Logix interpreter 9.5367431640625e-07 |
| P3 | Same sequence behaviour: counters, reject lock, master-part request | station cases 15 to 20 passed; counters after the bench 5 total, 2 OK, 3 NOK, 3 rejects confirmed, the values the earlier project's translator test asserts |
| P4 | Station logic unchanged; every change listed with its reason | findings table in the README |
| P5 | Build without errors and warnings | CODESYS `Compile complete -- 0 errors, 0 warnings`; Siemens PLC with alarms `errors=0 warnings=0` (`results/tia_hmi_build.txt`); Logix not compiled, structural check 0 findings |
| P6 | Code importable into the target tool | PLCopen XML exported, import into Machine Expert not tried; L5X written, import into Logix Designer not tried |
| P7 | Same operator screen on each platform | **not met.** CODESYS: a visualization bound to station variables compiles (0 errors, 0 warnings), layout from the CODESYS sample, no rendering. Siemens: 36 HMI-internal tags and 4 screens imported, no PLC connection, panel compile 40 errors. Logix: specification with a generated drawing |

## 4. Architecture of the port

| Layer | Siemens | CODESYS | Change |
|---|---|---|---|
| Curve evaluation | `FB_CurveEval` | `FB_CurveEval` | syntax only |
| Station sequence | `FB_HandleStation`, recipe written into its `Eval` by the caller | same, plus `VAR_IN_OUT Rcp : ST_EvalRecipe`, copied into `Eval` at the tare | instance access; `sT` renamed |
| Test data | `DB_TestData` with start values in `BEGIN` | `GVL_TestData` with initialisers, generated | form of start values |
| Result | `DB_TestResult` | `GVL_TestResult` | none in content |
| Cyclic call | OB1 `Main` and instance DB | `PLC_PRG` in `MainTask`, 10 ms | task model |

Logix: `AOI_CurveEval` and `AOI_HandleStation` with the recipe as InOut UDT, the counters as InOut `DINT[32]`, `AOI_CurveEval` nested as a local tag; the bench is a routine in a continuous task, the station a routine in a periodic task (2 ms) with six `ALMD` alarms. Details: `logix/README.md`.

Copying the recipe at the tare, and not on every call, keeps the cycle load flat (two arrays of 64 Reals per part, not per cycle) and means a recipe change takes effect with the next part, never in the middle of a pull.

## 5. Verification

| What | Method | Evidence |
|---|---|---|
| CODESYS port compiles | CODESYS V3.5 SP22 Patch 1 script engine, no window, `rebuild` | `results/codesys_build.txt` |
| CODESYS port behaves the same | bench in simulation mode, values read by script | `results/codesys_bench.json`, 20 of 20 |
| Siemens sources behave as recorded | float32 SCL translator, in CI | `tests/test_bench.py`, 20 of 20 |
| CODESYS test data equal to the Siemens data block | regenerated and compared, in CI | `tests/test_bench.py` |
| Siemens compile and S7-PLCSIM run | earlier project | its `results/tia_compile_testbench.txt` and `docs/PLCSIM_RUN.md` |
| Siemens station with alarms and panel | TIA Portal V18 Openness, no user interface | `results/tia_hmi_build.txt`, `results/tia_hmi_build_attempts.txt` |
| Logix file follows the rules read | structural check in this repo, in CI | `results/l5x_check.txt`, 0 findings; the check is shown to catch three planted errors (`tests/test_logix.py`) |
| Logix Structured Text gives the same results | subset interpreter in this repo, in CI | `results/logix_interpreter_bench.json`, 20 of 20; a planted wrong comparison makes it fail |

The bench proves the same arithmetic and the same sequence for the same inputs. It does not prove timing: the plant stand-in advances with the same `CycleTime` the station counts with, so a station called from a task of a different period still passes. In this run the task period (10 ms) and `CycleTime` (2 ms) were different (the build script sets the task to 10 ms), and the bench passed.

## 6. Limits of this work

- CODESYS simulation mode in the development system; not Machine Expert, not a Modicon controller, not a soft PLC with real task timing.
- No panel runtime, WebVisu or PanelView ran; there is no screenshot of any screen. The WinCC panel has tags and screens but no PLC connection and does not compile clean (README).
- The Logix file was not compiled or imported. The interpreter assumes float32 arithmetic and the call rules read in 1756-PM010I; it is not a controller.
- The Rockwell manuals were read through public copies of 1756-PM010I (Feb 2018) and 1756-RM003P (Dec 2014); Rockwell's own servers refused the request. 1756-RM014 (Import/Export) could not be read.
- Retention and start-up after a warm or cold reset were not tested on either platform.
