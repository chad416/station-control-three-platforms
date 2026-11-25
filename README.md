# station-control-three-platforms

One test station, its control blocks moved from Siemens SCL to CODESYS V3 Structured Text: what the port forced, what stayed identical, and the same 20 self-checking test cases as the proof.

> **Simulation-only study, no hardware.** The station is the end-of-line force-travel test of a car door-handle unit from [door-handle-force-travel-test](https://github.com/chad416/door-handle-force-travel-test). Its SCL blocks and test bench are copied here unchanged (`siemens/scl/`).
>
> **What was run here:** the CODESYS V3.5 SP22 Patch 1 port was built by script without a window (0 errors, 0 warnings) and its test bench ran in CODESYS simulation mode: 20 of 20 cases passed (`results/codesys_build.txt`, `results/codesys_bench.json`). The Siemens sources ran through the float32 SCL translator of the earlier project: 20 of 20 (CI).
>
> **What was not verified:** CODESYS is the platform EcoStruxure Machine Expert is built on. The code was **not** opened in Machine Expert, and no Modicon controller or Harmony panel was used. The Siemens blocks were not recompiled in this repo; their TIA Portal V18 compile (0 errors, 0 warnings) and their S7-PLCSIM Advanced run (20 of 20) are records of the earlier project. **No operator screen was built on any platform** (no CODESYS visualization, no WinCC panel, no PanelView). **The Allen-Bradley port is written but not compiled** ([logix/README.md](logix/README.md)): no Rockwell software is installed; it passes a structural check and runs the 20 cases 20 of 20 in a subset interpreter written in this repo. See [What was not done](#what-was-not-done).

## The question

What has to change, and what must stay identical, when the control of one station moves between platforms; and how do you prove that the ports behave the same?

## The answer

1. **The logic stayed identical. Three things had to change, and the compiler found each one.** The CODESYS port is the SCL text with the Siemens syntax taken off (`#`, `REGION`, quoted global names, named `LIMIT` arguments). On top of that the CODESYS compiler refused two things the TIA compiler accepts:
   - `sT` as a variable name: 194 errors, starting with `C9 Unexpected token 'sT' found` (`results/codesys_build_attempt1.txt`). IEC identifiers are not case-sensitive, and `ST` is a keyword in CODESYS. Renamed to `sTim`.
   - The bench writes the evaluation recipe straight into the evaluation instance inside the station (`#Station.Eval.GateX := ...`). CODESYS: 28 times `C37 'Eval' is no input of 'FB_HandleStation'` (`results/codesys_build_attempt2.txt`). The station now takes the recipe as a structure by reference (`ST_EvalRecipe`, `VAR_IN_OUT Rcp`) and copies it into its own evaluation instance at the tare, once per part.

   After that: `Compile complete -- 0 errors, 0 warnings` (`results/codesys_build.txt`).

2. **The ports behave the same on all 20 cases.** The bench replays 10 recorded curves in 14 evaluation cases and runs the station through 6 sequence cases (good part, wrong hand, reject lock, unhooked lever, three rejects in a row, acknowledge). Each case checks verdict, NOK code and nine curve elements against expected values with a tolerance of 0.001.

| Platform | How it ran | Cases passed | Largest element difference | Bench calls |
|---|---|---|---|---|
| CODESYS V3.5 SP22 Patch 1, Control Win V3 x64 device, simulation mode | here, by script | **20 of 20** | 9.536743E-07 | 102 |
| Siemens SCL in the float32 translator (`tools/scl37.py`) | here and in CI | **20 of 20** | 9.5367431640625e-07 | 102 |
| Siemens S7-1513 in S7-PLCSIM Advanced V7.0 (TIA Portal V20) | in the earlier project, not rerun here | 20 of 20 | 7.629395E-06 | 102 |
| Allen-Bradley Logix | not written, not run | - | - | - |

   CODESYS and the translator agree to the last bit on the largest difference (2^-20). The simulated S7 CPU differs by one last bit somewhere (2^-17 is one step of a 32-bit Real between 64 and 128). Both are far below the tolerance, and no verdict moved.

3. **The one thing that decides whether the ports behave the same is the time base, and the bench cannot see it.** The blocks use no platform timer. Each block adds its `CycleTime` input on every call, and the station times part presence, clamp time-out and the reject warning that way. That is why the same text runs on both platforms. But it is only right if `CycleTime` equals the real period of the task that calls the block. In this run the CODESYS task ran every 10 ms while the bench passed `CycleTime := 0.002`, and the bench still passed 20 of 20, because the plant stand-in uses the same number. A port that calls the station from a task of another period, or from a free-running cycle, passes this bench and still times wrongly on the machine. The check has to be made where the task is configured.

## Findings: what the port forced

"Verified by": **executed here** (ran in this repo), **compiled here** (compiler output in `results/`), **earlier record** (run in the earlier project, not repeated), **not verified**.

| Topic | Siemens (TIA Portal SCL) | CODESYS V3.5 port | Verified by |
|---|---|---|---|
| Numeric types and rounding | Real 32-bit, Int 16-bit, DInt 32-bit | REAL, INT, DINT, same sizes; same text, no change | executed here: 20 of 20, max difference 9.536743E-07 |
| Timers and time base | no TON; time = sum of `CycleTime` | unchanged; task set to 10 ms by script, bench passes 0.002 s | executed here (bench passed with the mismatch, see answer 3) |
| Retention and start-up | test data blocks `NON_RETAIN` | plain `VAR_GLOBAL`, no `RETAIN`; behaviour after a warm or cold reset not tested | not verified |
| Array indexing | `Array[1..32]`, `Array[0..63]` | same bounds kept | compiled and executed here |
| Reading own outputs | the blocks write each output once at the end from static variables | accepted unchanged | compiled here |
| Instance data | caller may write into `Station.Eval` | refused (C37); recipe by reference, copied at tare | compiled here (`codesys_build_attempt2.txt`), executed here |
| Identifiers | `sT` accepted | refused: `ST` is a keyword, names not case-sensitive (C9) | compiled here (`codesys_build_attempt1.txt`) |
| Global data | data blocks `"DB".member` | global variable lists, `{attribute 'qualified_only'}`, `GVL.member` | compiled and executed here |
| Start values of data | `BEGIN` section of the data block | array initialisers in the declaration (`tools/testdata.py`) | executed here |
| Syntax | `#local`, `REGION`, `LIMIT(MN:=, IN:=, MX:=)` | no `#`, `{region}` pragma, `LIMIT(mn, in, mx)` | compiled here |
| Strings | not used in the blocks | not used | not verified |
| Alarms | not built | not built | not verified |
| HMI tag addressing | not built | not built | not verified |
| Scan and task model | bench in OB1, 102 calls | bench in the cyclic MainTask, 102 calls | executed here; earlier record for OB1 |

The short systems-engineering dossier (need, proof concept, requirements, architecture, verification, limits) is [DOSSIER.md](DOSSIER.md).

## How it was run

```
python tools/testdata.py                       # CODESYS test data list from the Siemens data block
powershell -ExecutionPolicy Bypass -File codesys\scripts\run_codesys.ps1
python -m pytest -q
```

`run_codesys.ps1` starts `CODESYS.exe --profile="CODESYS V3.5 SP22 Patch 1" --noUI --runscript=codesys\scripts\build_and_run.py` hidden. The script copies the installation's "Standard" project template, switches its device to CODESYS Control Win V3 x64 3.5.22.10, adds the sources from `codesys/src/`, rebuilds, writes every build message to `results/codesys_build.txt`, exports PLCopen XML to `codesys/plcopen/`, then sets simulation mode, logs in, starts, polls `GVL_TestResult.Done` and reads every result variable (`results/codesys_bench.json`). The bench finished 1.4 s after the start.

`codesys/plcopen/*.xml` are the PLCopen XML exports of the data type, the four function blocks, the two global variable lists and the program, for import into a CODESYS-based tool. They were not imported into Machine Expert.

## What was not done

- **No operator screen on any platform.** The CODESYS script API of this installation showed no call that creates a visualization (`create_textlist` and `create_imagepool` exist; none of the visualization names tried exists), and a visualization of the sample project that ships with CODESYS came out empty when exported to PLCopen XML. A visualization would have to be drawn in the CODESYS window, which was not allowed here. No WebVisu ran, so there are no screenshots.
- **Phase 2, the WinCC panel in TIA Portal V18 through Openness, was not started.** The time box ran out.
- **Phase 3, the Allen-Bradley port (L5X files, Add-On Instructions, checks, interpreter, PanelView specification), was not written.** No Rockwell software is installed here, and no Rockwell manual was read for this repo, so nothing in it says anything about Logix.
- The CODESYS run is a simulation inside the development system. No soft PLC, no real controller, no real task timing, no I/O.
- Machine Expert, Modicon hardware and Harmony panels were not used.

## Repo map

| Path | Content |
|---|---|
| `siemens/scl/` | The Siemens SCL blocks and test bench, copied from the door-handle project |
| `codesys/src/` | CODESYS V3.5 port: `ST_EvalRecipe`, `FB_CurveEval`, `FB_HandleStation`, bench, plant stand-in, global lists, `PLC_PRG` |
| `codesys/scripts/` | Headless build-and-run script for the CODESYS script engine and its PowerShell starter |
| `codesys/plcopen/` | PLCopen XML exported by CODESYS |
| `tools/testdata.py` | Test data from the Siemens data block to the CODESYS list and `results/testdata.json` |
| `tools/scl37.py` | SCL translator (float32), copied from the door-handle project |
| `results/` | Build records of the three CODESYS attempts, bench result |
| `DOSSIER.md` | Short dossier |
| `tests/` | CI: Siemens bench in the translator, generated test data, CODESYS run record |

MIT licence.
