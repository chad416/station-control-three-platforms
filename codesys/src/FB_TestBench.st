FUNCTION_BLOCK FB_TestBench
//  CODESYS V3.5 port of siemens/scl/test/FB_TestBench.scl. Changes: sT is sTim; the station recipe is
//  the local structure StationRcp, passed to the station as Rcp (Siemens: Station.Eval.* written directly).
//  Called from OB1 every cycle. Needs no input from outside. Finishes on its own, then holds its
//  result in DB_TestResult.
//  Part 1, replay cases 1..NCases (DB_TestData): a recorded curve goes sample by sample into
//    FB_CurveEval. Verdict, NOK code, the nine elements and the envelope counts must equal the
//    values the NumPy evaluation gave for the same samples (elements within DB_TestData.Tol).
//  Part 2, six station cases: FB_HandleStation runs against FB_TestPlant.
//    NCases+1  good LH unit is clamped, pulled and passed
//    NCases+2  RH unit on an LH recipe: reject code 20, axis and clamp never move
//    NCases+3  reject lock: a chute signal while the part is in the fixture does not open it, a new
//              part is not started, the chute signal after the fixture is empty opens it
//    NCases+4  unit with unhooked latch lever: pulled, reject code 5
//    NCases+5  third reject in a row: master part asked for, start blocked
//    NCases+6  after the acknowledge the good unit is pulled and passed
//  Check codes (DB_TestResult.FirstFailedCheck, CaseCheck): 0 passed.
//    Replay:  1 verdict, 2 NOK code, 3 FpG1, 4 FrG1, 5 FMean, 6 FHyst, 7 FpG2, 8 FPeak, 9 XPeak,
//             10 FStep, 11 XStop, 12 envelope nodes outside, 13 envelope nodes evaluated
//    Station: 21 verdict, 22 NOK code, 23 state, 24 counter, 25 axis or clamp moved (or did not),
//             26 reject lock opened too early or a part was started while locked,
//             27 reject lock not opened by the chute, 28 master-part request, 29 time-out
   VAR_INPUT
      ReplayPerCall : Int := 200;   // samples replayed per call
      ScansPerCall : Int := 100;   // station scans (2 ms of station time each) per call
   END_VAR

   VAR
      Eval : FB_CurveEval;
      Station : FB_HandleStation;
      Plant : FB_TestPlant;
      StationRcp : ST_EvalRecipe;   // recipe of the station (Siemens: written into Station.Eval)
      sPhase : Int;   // 0 start, 1 replay, 2 station, 3 done
      sSub : Int;
      sCase : Int;
      sIdx : Int;
      sCk : Int;
      sNok : Int;
      sRecord : Bool;
      sRun : Int;
      sPassed : Int;
      sFailed : Int;
      sFirstCase : Int;
      sFirstCheck : Int;
      sMaxErr : Real;
      sCalls : DInt;
      sMeas : Array[0..8] of Real;
      sStep : Int;
      sTim : Int;
      sPart : Bool;
      sLH : Bool;
      sRH : Bool;
      sChute : Bool;
      sAck : Bool;
      sPlantReset : Bool;
      sCurve : Int;
   END_VAR

   VAR_TEMP
      tI : Int;
      tJ : Int;
      tB : Int;
      tCurve : Int;
      tMode : Int;
      tA : Int;
      tN : Int;
      tStroke : Int;
      tErr : Real;
   END_VAR

(* @IMPLEMENTATION *)
    {region "Start"}
        IF sPhase = 0 THEN
            FOR tI := 1 TO 32 DO
                GVL_TestResult.CasePass[tI] := FALSE;
                GVL_TestResult.CaseCheck[tI] := 0;
                GVL_TestResult.CaseNok[tI] := 0;
            END_FOR;
            // the part of the recipe that is the same in every case, for both evaluation instances
            Eval.GateX := GVL_TestData.GateX;
            Eval.Gate2X := GVL_TestData.Gate2X;
            Eval.PeakXLo := GVL_TestData.PeakXLo;
            Eval.PeakXHi := GVL_TestData.PeakXHi;
            Eval.StepSpan := GVL_TestData.StepSpan;
            Eval.StopF := GVL_TestData.StopF;
            Eval.EnvX0 := GVL_TestData.EnvX0;
            Eval.EnvDx := GVL_TestData.EnvDx;
            Eval.EnvN := GVL_TestData.EnvN;
            StationRcp.GateX := GVL_TestData.GateX;
            StationRcp.Gate2X := GVL_TestData.Gate2X;
            StationRcp.PeakXLo := GVL_TestData.PeakXLo;
            StationRcp.PeakXHi := GVL_TestData.PeakXHi;
            StationRcp.StepSpan := GVL_TestData.StepSpan;
            StationRcp.StopF := GVL_TestData.StopF;
            StationRcp.EnvX0 := GVL_TestData.EnvX0;
            StationRcp.EnvDx := GVL_TestData.EnvDx;
            StationRcp.EnvN := GVL_TestData.EnvN;
            FOR tI := 0 TO 63 DO
                Eval.EnvLo[tI] := GVL_TestData.EnvLo[tI];
                Eval.EnvHi[tI] := GVL_TestData.EnvHi[tI];
                StationRcp.EnvLo[tI] := GVL_TestData.EnvLo[tI];
                StationRcp.EnvHi[tI] := GVL_TestData.EnvHi[tI];
            END_FOR;
            // the station judges with windows + return stroke (mode 3: limits 32..47)
            StationRcp.Mode := 3;
            StationRcp.G1Lo := GVL_TestData.Lim[32];
            StationRcp.G1Hi := GVL_TestData.Lim[33];
            StationRcp.MeanLo := GVL_TestData.Lim[34];
            StationRcp.MeanHi := GVL_TestData.Lim[35];
            StationRcp.HystLo := GVL_TestData.Lim[36];
            StationRcp.HystHi := GVL_TestData.Lim[37];
            StationRcp.RetFMin := GVL_TestData.Lim[38];
            StationRcp.G2Lo := GVL_TestData.Lim[39];
            StationRcp.G2Hi := GVL_TestData.Lim[40];
            StationRcp.PeakFLo := GVL_TestData.Lim[41];
            StationRcp.PeakFHi := GVL_TestData.Lim[42];
            StationRcp.PeakXMin := GVL_TestData.Lim[43];
            StationRcp.PeakXMax := GVL_TestData.Lim[44];
            StationRcp.StepLo := GVL_TestData.Lim[45];
            StationRcp.StopXLo := GVL_TestData.Lim[46];
            StationRcp.StopXHi := GVL_TestData.Lim[47];
            sCase := 1;
            sSub := 0;
            sCk := 0;
            sNok := 0;
            sStep := 10;
            sTim := 0;
            sPhase := 1;
        END_IF;
        IF sPhase < 3 THEN
            sCalls := sCalls + 1;
        END_IF;
    {endregion}

    {region "Replay"}
        IF sPhase = 1 THEN
            FOR tI := 1 TO ReplayPerCall DO
                IF NOT sRecord THEN
                    tCurve := GVL_TestData.CaseCurve[sCase];
                    tMode := GVL_TestData.CaseMode[sCase];
                    tA := GVL_TestData.CurveStart[tCurve];
                    tN := GVL_TestData.CurveNPull[tCurve];
                    CASE sSub OF
                        0:  // limits of the mode of this case, clear the evaluation
                            tB := (tMode - 1) * 16;
                            Eval.Mode := tMode;
                            Eval.G1Lo := GVL_TestData.Lim[tB];
                            Eval.G1Hi := GVL_TestData.Lim[tB + 1];
                            Eval.MeanLo := GVL_TestData.Lim[tB + 2];
                            Eval.MeanHi := GVL_TestData.Lim[tB + 3];
                            Eval.HystLo := GVL_TestData.Lim[tB + 4];
                            Eval.HystHi := GVL_TestData.Lim[tB + 5];
                            Eval.RetFMin := GVL_TestData.Lim[tB + 6];
                            Eval.G2Lo := GVL_TestData.Lim[tB + 7];
                            Eval.G2Hi := GVL_TestData.Lim[tB + 8];
                            Eval.PeakFLo := GVL_TestData.Lim[tB + 9];
                            Eval.PeakFHi := GVL_TestData.Lim[tB + 10];
                            Eval.PeakXMin := GVL_TestData.Lim[tB + 11];
                            Eval.PeakXMax := GVL_TestData.Lim[tB + 12];
                            Eval.StepLo := GVL_TestData.Lim[tB + 13];
                            Eval.StopXLo := GVL_TestData.Lim[tB + 14];
                            Eval.StopXHi := GVL_TestData.Lim[tB + 15];
                            Eval(Reset := TRUE, Sample := FALSE, Stroke := 0, X := 0.0, F := 0.0, Finish := FALSE);
                            sIdx := 0;
                            sSub := 1;
                        1:  // one sample: the pull samples first, then the return samples
                            IF sIdx < tN THEN
                                tStroke := 1;
                            ELSE
                                tStroke := 2;
                            END_IF;
                            Eval(Reset := FALSE, Sample := TRUE, Stroke := tStroke,
                                  X := GVL_TestData.X[tA + sIdx], F := GVL_TestData.F[tA + sIdx], Finish := FALSE);
                            sIdx := sIdx + 1;
                            IF sIdx >= 2 * tN THEN
                                sSub := 2;
                            END_IF;
                        2:  // judge and compare with the expected values
                            Eval(Reset := FALSE, Sample := FALSE, Stroke := 0, X := 0.0, F := 0.0, Finish := TRUE);
                            sMeas[0] := Eval.FpG1;
                            sMeas[1] := Eval.FrG1;
                            sMeas[2] := Eval.FMean;
                            sMeas[3] := Eval.FHyst;
                            sMeas[4] := Eval.FpG2;
                            sMeas[5] := Eval.FPeak;
                            sMeas[6] := Eval.XPeak;
                            sMeas[7] := Eval.FStep;
                            sMeas[8] := Eval.XStop;
                            IF Eval.Ok XOR GVL_TestData.ExpOk[sCase] THEN
                                sCk := 1;
                            ELSIF Eval.NokCode <> GVL_TestData.ExpNok[sCase] THEN
                                sCk := 2;
                            ELSIF Eval.EnvViol <> GVL_TestData.ExpEnvViol[sCase] THEN
                                sCk := 12;
                            ELSIF Eval.EnvNodes <> GVL_TestData.ExpEnvNodes[sCase] THEN
                                sCk := 13;
                            END_IF;
                            FOR tJ := 0 TO 8 DO
                                tB := (sCase - 1) * 9 + tJ;
                                IF GVL_TestData.ExpFeatValid[tB] THEN
                                    tErr := ABS(sMeas[tJ] - GVL_TestData.ExpFeat[tB]);
                                    IF tErr > sMaxErr THEN
                                        sMaxErr := tErr;
                                    END_IF;
                                    IF tErr > GVL_TestData.Tol AND sCk = 0 THEN
                                        sCk := 3 + tJ;
                                    END_IF;
                                END_IF;
                            END_FOR;
                            sNok := Eval.NokCode;
                            sSub := 0;
                            sRecord := TRUE;
                    END_CASE;
                END_IF;
            END_FOR;
        END_IF;
    {endregion}

    {region "Station"}
        IF sPhase = 2 THEN
            FOR tI := 1 TO ScansPerCall DO
                IF sPhase = 2 AND NOT sRecord THEN
                    IF sTim < 30000 THEN
                        sTim := sTim + 1;
                    END_IF;
                    // what the operator and the line do, and what the station must have done by now
                    CASE sStep OF
                        10:  // good LH unit
                            sPart := TRUE;
                            sLH := TRUE;
                            sRH := FALSE;
                            sCurve := GVL_TestData.GoodCurve;
                            sPlantReset := TRUE;
                            sStep := 11;
                            sTim := 0;
                        11:
                            IF Station.CntTotal >= 1 OR sTim > 4000 THEN
                                IF sTim > 4000 THEN
                                    sCk := 29;
                                ELSIF Station.Verdict <> 1 THEN
                                    sCk := 21;
                                ELSIF Station.NokCode <> 0 THEN
                                    sCk := 22;
                                ELSIF Station.CntOk <> 1 OR Station.CntNok <> 0 THEN
                                    sCk := 24;
                                ELSIF NOT Plant.Moved THEN
                                    sCk := 25;
                                END_IF;
                                sNok := Station.NokCode;
                                sRecord := TRUE;
                                sPart := FALSE;
                                sStep := 12;
                                sTim := 0;
                            END_IF;
                        12:  // unit taken out
                            IF Station.State = 0 OR sTim > 4000 THEN
                                sStep := 20;
                                sTim := 0;
                            END_IF;
                        20:  // RH unit while LH units are built
                            sPart := TRUE;
                            sLH := FALSE;
                            sRH := TRUE;
                            sCurve := GVL_TestData.GoodCurve;
                            sPlantReset := TRUE;
                            sStep := 21;
                            sTim := 0;
                        21:
                            IF Station.CntTotal >= 2 OR sTim > 4000 THEN
                                IF sTim > 4000 THEN
                                    sCk := 29;
                                ELSIF Station.Verdict <> 2 THEN
                                    sCk := 21;
                                ELSIF Station.NokCode <> 20 THEN
                                    sCk := 22;
                                ELSIF Station.State <> 8 THEN
                                    sCk := 23;
                                ELSIF Plant.Moved OR Plant.Pos > 0.0 OR NOT Plant.ClampOpen THEN
                                    sCk := 25;
                                END_IF;
                                sNok := Station.NokCode;
                                sRecord := TRUE;
                                sStep := 22;
                                sTim := 0;
                            END_IF;
                        22:  // reject lock: a chute signal while the rejected unit is still in the fixture
                            sChute := sTim >= 5 AND sTim < 10;
                            IF sTim >= 20 THEN
                                IF Station.State <> 8 OR NOT Station.Locked THEN
                                    sCk := 26;
                                END_IF;
                                sPart := FALSE;
                                sStep := 23;
                                sTim := 0;
                            END_IF;
                        23:  // the unit is taken out and a new good unit is put in without using the chute
                            IF sTim = 20 THEN
                                sPart := TRUE;
                                sLH := TRUE;
                                sRH := FALSE;
                                sPlantReset := TRUE;
                            END_IF;
                            IF sTim >= 400 THEN
                                IF sCk = 0 AND (Station.State <> 8 OR Station.CntTotal <> 2 OR Plant.Moved) THEN
                                    sCk := 26;
                                END_IF;
                                sPart := FALSE;
                                sStep := 24;
                                sTim := 0;
                            END_IF;
                        24:  // fixture empty, the chute sensor sees a part
                            sChute := sTim >= 20 AND sTim < 25;
                            IF sTim >= 40 THEN
                                IF sCk = 0 AND (Station.State <> 0 OR Station.Locked OR Station.CntRejectConfirmed <> 1) THEN
                                    sCk := 27;
                                END_IF;
                                sNok := Station.NokCode;
                                sRecord := TRUE;
                                sStep := 30;
                                sTim := 0;
                            END_IF;
                        30:  // LH unit with unhooked latch lever
                            sPart := TRUE;
                            sLH := TRUE;
                            sRH := FALSE;
                            sCurve := GVL_TestData.BadCurve;
                            sPlantReset := TRUE;
                            sStep := 31;
                            sTim := 0;
                        31:
                            IF Station.CntTotal >= 3 OR sTim > 4000 THEN
                                IF sTim > 4000 THEN
                                    sCk := 29;
                                ELSIF Station.Verdict <> 2 THEN
                                    sCk := 21;
                                ELSIF Station.NokCode <> 5 THEN
                                    sCk := 22;
                                ELSIF Station.CntConsecNok <> 2 THEN
                                    sCk := 24;
                                ELSIF NOT Plant.Moved THEN
                                    sCk := 25;
                                END_IF;
                                sNok := Station.NokCode;
                                sRecord := TRUE;
                                sPart := FALSE;
                                sStep := 32;
                                sTim := 0;
                            END_IF;
                        32:  // into the chute
                            sChute := sTim >= 20 AND sTim < 25;
                            IF (sTim >= 40 AND Station.State = 0) OR sTim > 4000 THEN
                                sStep := 40;
                                sTim := 0;
                            END_IF;
                        40:  // the same defect again: third reject in a row
                            sPart := TRUE;
                            sCurve := GVL_TestData.BadCurve;
                            sPlantReset := TRUE;
                            sStep := 41;
                            sTim := 0;
                        41:
                            IF Station.CntTotal >= 4 OR sTim > 4000 THEN
                                IF sTim > 4000 THEN
                                    sCk := 29;
                                ELSIF Station.Verdict <> 2 THEN
                                    sCk := 21;
                                ELSIF Station.NokCode <> 5 THEN
                                    sCk := 22;
                                ELSIF Station.CntConsecNok <> 3 THEN
                                    sCk := 24;
                                END_IF;
                                sNok := Station.NokCode;
                                sPart := FALSE;
                                sStep := 42;
                                sTim := 0;
                            END_IF;
                        42:  // into the chute; then a good unit is put in
                            sChute := sTim >= 20 AND sTim < 25;
                            IF sTim >= 40 THEN
                                IF sCk = 0 AND Station.State <> 0 THEN
                                    sCk := 27;
                                ELSIF sCk = 0 AND (NOT Station.RigCheckRequired OR NOT Station.QCallOperator) THEN
                                    sCk := 28;
                                END_IF;
                                sPart := TRUE;
                                sCurve := GVL_TestData.GoodCurve;
                                sPlantReset := TRUE;
                                sStep := 43;
                                sTim := 0;
                            END_IF;
                        43:  // the start must stay blocked until the acknowledge
                            IF sTim >= 400 THEN
                                IF sCk = 0 AND (Station.State <> 0 OR Station.CntTotal <> 4 OR Plant.Moved) THEN
                                    sCk := 28;
                                END_IF;
                                sRecord := TRUE;
                                sStep := 50;
                                sTim := 0;
                            END_IF;
                        50:  // acknowledge key; the good unit is then tested
                            sAck := sTim < 5;
                            IF Station.CntTotal >= 5 OR sTim > 4000 THEN
                                IF sTim > 4000 THEN
                                    sCk := 29;
                                ELSIF Station.RigCheckRequired THEN
                                    sCk := 28;
                                ELSIF Station.Verdict <> 1 THEN
                                    sCk := 21;
                                ELSIF Station.NokCode <> 0 THEN
                                    sCk := 22;
                                ELSIF Station.CntOk <> 2 OR Station.CntConsecNok <> 0 THEN
                                    sCk := 24;
                                END_IF;
                                sNok := Station.NokCode;
                                sRecord := TRUE;
                                sPart := FALSE;
                                sAck := FALSE;
                                sStep := 51;
                                sTim := 0;
                            END_IF;
                        51:  // unit taken out
                            IF Station.State = 0 OR sTim > 4000 THEN
                                sStep := 99;
                            END_IF;
                        ELSE
                            sPhase := 3;
                    END_CASE;
                    Plant(Reset := sPlantReset, CycleTime := 0.002, QVel := Station.QVel,
                           QDriveEnable := Station.QDriveEnable, QClamp := Station.QClamp,
                           PartPresent := sPart, Curve := sCurve, Seat := 5.0);
                    sPlantReset := FALSE;
                    Station(Rcp := StationRcp, CycleTime := 0.002, SafetyOk := TRUE, DriveOk := TRUE, AckFault := sAck,
                             StartEnable := TRUE, PartPresent := sPart, SensLH := sPart AND sLH,
                             SensRH := sPart AND sRH, VariantLH := TRUE, ClampClosed := Plant.ClampClosed,
                             ClampOpen := Plant.ClampOpen, RejectChute := sChute, Pos := Plant.Pos,
                             Force := Plant.Force, Compliance := 0.0);
                END_IF;
            END_FOR;
        END_IF;
    {endregion}

    {region "Record"}
        IF sRecord THEN
            sRun := sRun + 1;
            IF sCk = 0 THEN
                sPassed := sPassed + 1;
                GVL_TestResult.CasePass[sCase] := TRUE;
            ELSE
                sFailed := sFailed + 1;
                IF sFirstCase = 0 THEN
                    sFirstCase := sCase;
                    sFirstCheck := sCk;
                END_IF;
            END_IF;
            GVL_TestResult.CaseCheck[sCase] := sCk;
            GVL_TestResult.CaseNok[sCase] := sNok;
            sCase := sCase + 1;
            sCk := 0;
            sNok := 0;
            sRecord := FALSE;
            IF sPhase = 1 AND sCase > GVL_TestData.NCases THEN
                sPhase := 2;
            END_IF;
        END_IF;
    {endregion}

    {region "Result"}
        GVL_TestResult.CasesTotal := GVL_TestData.NCases + 6;
        GVL_TestResult.CasesRun := sRun;
        GVL_TestResult.CasesPassed := sPassed;
        GVL_TestResult.CasesFailed := sFailed;
        GVL_TestResult.FirstFailedCase := sFirstCase;
        GVL_TestResult.FirstFailedCheck := sFirstCheck;
        GVL_TestResult.MaxFeatError := sMaxErr;
        GVL_TestResult.BenchCalls := sCalls;
        GVL_TestResult.Done := sPhase = 3;
        GVL_TestResult.AllPassed := sPhase = 3 AND sFailed = 0 AND sPassed = GVL_TestData.NCases + 6;
    {endregion}
END_FUNCTION_BLOCK
