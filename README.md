# station-control-three-platforms

> **Status: no operator screen is finished.** CODESYS: a visualization bound to station variables compiles, but its layout is the CODESYS sample's. Siemens: 36 tags (HMI-internal, not linked to the PLC) and the four screens are imported into the KTP700 Basic, but the panel compile still ends with 40 errors and there is no PLC connection. Allen-Bradley: specification only. Control code and the 20-case proof cover the three platforms as far as the table below says.

One test station, its control blocks moved from Siemens SCL to CODESYS V3 Structured Text and to Allen-Bradley Logix Add-On Instructions: what the port forced, what stayed identical, and the same 20 self-checking test cases as the proof.

> **Simulation-only study, no hardware.** The station is the end-of-line force-travel test of a car door-handle unit from [door-handle-force-travel-test](https://github.com/chad416/door-handle-force-travel-test). Its SCL blocks and test bench are copied here unchanged (`siemens/scl/`).
>
> **How far each platform got:**
>
> | Platform | Control code | Bench, 20 cases | Operator screen |
> |---|---|---|---|
> | Schneider side: CODESYS V3.5 SP22 Patch 1 (the base of EcoStruxure Machine Expert) | **compiled here**, 0 errors, 0 warnings | **executed here** in CODESYS simulation mode: 20 of 20 | a visualization bound to station variables **compiled here** (0 errors, 0 warnings); no screenshot: simulation mode serves no WebVisu |
> | Siemens: TIA Portal V18, S7-1513 | **compiled here** with the alarm block, 0 errors, 0 warnings; bench compiled and run in S7-PLCSIM in the earlier project | 20 of 20 in the float32 SCL translator (CI); S7-PLCSIM record of the earlier project | **imported, not compiled clean**: KTP700 Basic with 36 HMI-internal tags and 4 screens; no PLC connection; panel compile `errors=40 warnings=0` |
> | Allen-Bradley: Studio 5000 Logix Designer | **written, not compiled**: no Rockwell software here | 20 of 20 in a subset interpreter written in this repo (CI), not on a controller | **specification only** |
>
> **Not verified:** nothing was opened in Machine Expert, no Modicon controller or Harmony panel was used, nothing ran on a Logix controller or emulator, no panel runtime was started, no real task timing was measured. Pictures: the only one is [docs/img/screen_spec.svg](docs/img/screen_spec.svg), a **generated drawing** of the screen specification, not a screenshot.

## The question

What has to change, and what must stay identical, when the control and the operator screen of one station move between Siemens, a CODESYS-based controller and Allen-Bradley Logix; and how do you prove that the ports behave the same?

## The answer

1. **The station logic stayed identical on all three. What changed was forced at the edges, and on two platforms a tool found each change.**
   - CODESYS refused two things the TIA compiler accepts. `sT` as a variable name gave 194 errors, starting with `C9 Unexpected token 'sT' found` (`results/codesys_build_attempt1.txt`): names are not case-sensitive and `ST` is a keyword. The bench writes the recipe straight into the evaluation instance inside the station (`#Station.Eval.GateX := ...`): 28 times `C37 'Eval' is no input of 'FB_HandleStation'` (`results/codesys_build_attempt2.txt`). The station now takes the recipe as a structure by reference (`ST_EvalRecipe`) and copies it into its evaluation instance at the tare, once per part.
   - Logix has the same wall, plus one more. An Add-On Instruction's Input and Output parameters may only be BOOL, SINT, INT, DINT or REAL (Rockwell 1756-PM010I p. 43), so the recipe with its envelope arrays and the counter array become InOut parameters. Local tags cannot be read from outside an AOI (p. 19), so the operator screen cannot reach `Station.Eval.FpG1` as it can on Siemens; the station AOI gets nine extra outputs for the screen. Arrays have a size, not bounds: `Array[1..32]` becomes `[33]` with element 0 unused.
   - The Siemens panel reads the station through a standard-access data block (`DB_HMI`), because the station data is in optimized blocks and the panel connection used here is addressed absolutely.

2. **The ports behave the same on all 20 cases, where they could be run.** The bench replays 10 recorded curves in 14 evaluation cases and runs the station through 6 sequence cases (good part, wrong hand, reject lock, unhooked lever, three rejects in a row, acknowledge). Each case checks verdict, NOK code and nine curve elements against expected values, tolerance 0.001.

| Platform | How it ran | Cases passed | Largest element difference | Bench calls |
|---|---|---|---|---|
| CODESYS V3.5 SP22 Patch 1, Control Win V3 x64 device, simulation mode | executed here, by script | **20 of 20** | 9.536743E-07 | 102 |
| Siemens SCL in the float32 translator (`tools/scl37.py`) | executed here and in CI | **20 of 20** | 9.5367431640625e-07 | 102 |
| Siemens S7-1513 in S7-PLCSIM Advanced V7.0 (TIA Portal V20) | earlier project, not rerun here | 20 of 20 | 7.629395E-06 | 102 |
| Logix L5X in the subset interpreter (`tools/logix_st.py`) | executed here and in CI; **not a controller** | **20 of 20** | 9.5367431640625e-07 | 102 |

   CODESYS, the SCL translator and the Logix interpreter agree to the last bit on the largest difference (2^-20). The simulated S7 CPU differs by one last bit somewhere (2^-17). All are far below the tolerance, and no verdict moved. The Logix line shows only that the Structured Text in the L5X gives these results under the arithmetic the interpreter assumes (float32 per operation); how a Logix controller rounds was not read in a manual and not tested.

3. **The one thing that decides whether the ports behave the same is the time base, and the bench cannot see it.** The blocks use no platform timer. Each block adds its `CycleTime` input on every call, and the station times part presence, clamp time-out and the reject warning that way. That is why the same logic runs on all three. But it is only right if `CycleTime` equals the real period of the task that calls the station. In this run the CODESYS task ran every 10 ms while the bench passed `CycleTime := 0.002`, and the bench still passed 20 of 20, because the plant stand-in uses the same number. The Logix file puts the station in a periodic task with Rate 2 ms next to `CycleTime := 0.002`; the Siemens panel project calls it in OB1, which has no fixed period, and says so in the block. On every platform the check has to be made where the task is configured.

## Findings: what the port forced

"Verified by": **executed here**, **compiled here** (compiler output in `results/`), **checked here** (structural check or interpreter in this repo, no vendor tool), **read in the vendor manual** (source named), **earlier record** (earlier project), **not verified**.

| Topic | Siemens (TIA Portal SCL) | CODESYS V3.5 | Logix (Studio 5000) | Verified by |
|---|---|---|---|---|
| Numeric types and rounding | Real 32-bit, Int 16-bit, DInt 32-bit | same sizes, same text | REAL, INT, DINT; mixed INT/REAL written without conversion functions | CODESYS executed here, max difference 9.536743E-07; Logix checked here under an assumed float32 rule, its real rounding not verified |
| Timers and time base | no TON; time = sum of `CycleTime`; OB1 in the panel project | unchanged; task 10 ms, `CycleTime` 0.002 s | unchanged; periodic task Rate 2 ms written next to `CycleTime := 0.002` | CODESYS executed here (passed with the mismatch); Logix not verified |
| Retention and start-up | data blocks `NON_RETAIN` | plain `VAR_GLOBAL`, no `RETAIN` | no first-scan handling written; Logix retention not read in a manual | not verified on any platform |
| Array indexing | `Array[1..32]`, `Array[0..63]` | same bounds kept | size only: `[33]`, element 0 unused; `[64]` | CODESYS compiled and executed here; Logix checked here (interpreter raises on any index outside), form from public L5X examples |
| Reading own outputs | blocks write each output once at the end | accepted unchanged | accepted by the interpreter | CODESYS compiled here; Logix not verified |
| Instance data | caller writes into `Station.Eval`; panel can read it | refused (C37): recipe by reference, copied at tare | AOI Input/Output atomic only (PM010 p. 43): recipe and counters are InOut; locals not reachable (p. 19): nine `E_` outputs for the screen | CODESYS compiled here; Logix read in the vendor manual and checked here (rules A1, A2, S2) |
| Nested instances | multi-instance `Eval` in the station | same | local tag of AOI type, nesting allowed (PM010 pp. 28-29) | CODESYS compiled here; Logix read in the vendor manual |
| Calls | named parameters | named parameters | instance tag first, then required arguments (PM010 p. 76); inputs written as `Eval.Reset := 1` before the call | CODESYS compiled here; Logix read in the vendor manual, checked here (A7) |
| Identifiers | `sT` accepted | refused, `ST` is a keyword (C9) | renamed as in CODESYS; names at most 40 characters (PM010 p. 41) | CODESYS compiled here; Logix checked here |
| Global data | data blocks `"DB".member` | global variable lists, `qualified_only` | controller tags `TD_*`, `TR_*`; an AOI sees only its parameters and locals, so the bench is a routine, not an AOI | CODESYS compiled and executed here; Logix checked here (S2) |
| Start values | `BEGIN` section | array initialisers | decorated tag data in the L5X | CODESYS executed here; Logix checked here (interpreter reads them) |
| Strings | NOK reason as a code | as a code | as a code | not verified: no platform shows a text list in a run |
| Alarms | `Program_Alarm` instances in the CPU (`FB_StationAlarms`) | not built | six `ALMD` instructions, syntax from RM003 pp. 44-46 | Siemens compiled here; Logix read in the vendor manual, not compiled; CODESYS not done |
| HMI tag addressing | absolute tags into `DB_HMI` written; imported only as HMI-internal tags (no connection) | visualization reads `PLC_PRG.Bench.Station.Locked` by name | screen tags must be AOI parameters, not locals | Siemens: `DB_HMI` compiled here, 36 internal tags and 4 screens imported, panel compile 40 errors; CODESYS compiled here; Logix specification |
| Scan and task model | bench in OB1, 102 calls | cyclic MainTask, 102 calls | continuous task for the bench, periodic task for the station | CODESYS executed here; S7 earlier record; Logix interpreter only |

## The Siemens panel: what was built and what is missing

`siemens/scripts/tia_hmi.ps1` builds a TIA Portal V18 project through Openness without user interface (`results/tia_hmi_build.txt`):

- S7-1513 with `FB_CurveEval`, `FB_HandleStation`, the alarm block `FB_StationAlarms` (six `Program_Alarm` instances), `DB_HMI` and OB1: `COMPILE PLC Success  errors=0  warnings=0`.
- A KTP700 Basic (`6AV2 123-2GB03-0AX0`, device version 17.0.0.0; version 18.0.0.0 was not found in the catalogue), both devices on subnet `PN/IE_1` (PLC 192.168.0.1, panel 192.168.0.2).
- **Imported, one object per TIA session** (`siemens/scripts/tia_hmi_step.ps1`, record `results/tia_hmi_steps.txt`), because after a refused import every later call failed with `Access to a disposed object` (HMI target, then device, project and TIA Portal session; `results/tia_hmi_build_attempts.txt`):
  - **36 tags**, as HMI-internal tags (`siemens/hmi/xml/tags_Station_internal.xml`). The wrong part had been the `DataType` link on each tag: with it TIA refused the first Real tag, `The import of tag TCycle was aborted, because the Coding property is read-only`. Without it, `IMPORT ok`.
  - **4 screens** (Station, Measurement, Alarms, Setup) with text fields, output fields and navigation buttons: `IMPORT ok`. The first compile showed that an output field needs a format pattern (`The format pattern specified for 'VState' is invalid`); with `s999999` (Int), `s9999999999` (DInt) and `9` (Bool) those errors went away.
- **Not done:**
  - **No PLC connection.** The driver string was the first wrong value: `SIMATIC S7 1500` is refused (`The value 'SIMATIC S7 1500' for the attribute 'Driver' is not supported`). `S7_1500_OMS` and `S7_1500`, the PLC ids in the installed communication channel files, were no longer reported. But every `InterfaceType` tried was refused (`Ethernet`, none, `PROFINET (X1)`, a dummy): `The value 'Ethernet' of attribute 'InterfaceType' is incompatible with other attributes`. So the tags are HMI-internal and show nothing from the PLC.
  - **The panel compile ends `COMPILE HMI Error errors=40 warnings=0`:** 23 times `The format pattern specified for '...' is invalid`, all on Real fields (pattern `s99999.999`); 16 times `The parameter of a function is not available for trigger Nav..., event 'Click'. This parameter must be assigned a valid value` (the `ActivateScreen` parameter); once `No start screen defined`. The start screen was not set, because the time box ended.
- There is no picture of a WinCC screen. The WinCC runtime simulator was not started.


The short systems-engineering dossier is [DOSSIER.md](DOSSIER.md). The Logix details, the manuals read and what each check proves: [logix/README.md](logix/README.md). The screen specification: [logix/PANELVIEW_SPEC.md](logix/PANELVIEW_SPEC.md), drawn in [docs/img/screen_spec.svg](docs/img/screen_spec.svg) (generated).

## How it was run

```
python tools/testdata.py                       # CODESYS test data list from the Siemens data block
powershell -ExecutionPolicy Bypass -File codesys\scripts\run_codesys.ps1                       # CODESYS build + bench
powershell -ExecutionPolicy Bypass -File codesys\scripts\run_codesys.ps1 -Script visu_try.py   # CODESYS visualization
python siemens/hmi/make_hmi_xml.py
powershell -ExecutionPolicy Bypass -File siemens\scripts\tia_hmi.ps1                           # TIA Portal V18: PLC, panel device, network (-TryImports: the refused HMI imports)
python tools/make_logix.py                      # logix/StationPort.L5X
python tools/l5x_check.py                       # structural check
python tools/logix_st.py                        # 20 cases in the subset interpreter
python -m pytest -q
```

CODESYS runs as `CODESYS.exe --profile="CODESYS V3.5 SP22 Patch 1" --noUI --runscript=...`, started hidden. TIA Portal runs through Openness with `TiaPortalMode.WithoutUserInterface`. No window of either tool was opened, and no panel runtime or simulator was started.

The CODESYS visualization is the visualization of the sample project that ships with CODESYS, exported in the native format by the script engine, with its five variables, texts and start visualization replaced by the station's (`codesys/scripts/derive_visu.py`). The first import built with 2 errors (`Start visualization <Diagnosis> does not exist`, `<Live_Visu>`), the second, with the start visualization renamed, with 0 errors and 0 warnings (`results/codesys_visu_attempt.txt`). Its layout and element types are the sample's, so it is not the screen of the specification. The derived files are not in the repo, because they are the vendor's sample. The simulation then ran, but `http://localhost:8080/webvisu.htm` gave "Unable to connect to the remote server": simulation mode serves no WebVisu, so there is no screenshot.

## Repo map

| Path | Content |
|---|---|
| `siemens/scl/` | The Siemens SCL blocks and test bench, copied from the door-handle project |
| `siemens/scl/hmi/` | Alarm block with `Program_Alarm`, the panel's data block `DB_HMI`, OB1 for the panel project |
| `siemens/hmi/` | Generator of the WinCC import files and the files (refused by TIA, see above) |
| `siemens/scripts/tia_hmi.ps1` | TIA Portal V18 Openness build: PLC with alarms, panel device, network |
| `codesys/src/` | CODESYS V3.5 port: `ST_EvalRecipe`, `FB_CurveEval`, `FB_HandleStation`, bench, plant stand-in, global lists, `PLC_PRG` |
| `codesys/scripts/` | Headless build-and-run, visualization try, its derivation |
| `codesys/plcopen/` | PLCopen XML exported by CODESYS (not imported anywhere) |
| `logix/` | `StationPort.L5X` (not compiled), its ST sources, README with the manuals read, PanelView specification |
| `tools/` | test data, SCL translator, L5X generator, structural check, Logix subset interpreter, screen drawing |
| `results/` | Build records, bench results, check output |
| `tests/` | CI: Siemens bench in the translator, generated files, run records, L5X checks and interpreter |
| `DOSSIER.md` | Short dossier |

MIT licence.
