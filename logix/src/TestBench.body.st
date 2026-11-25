
    // --- Start ---
        IF sPhase = 0 THEN
            FOR tI := 1 TO 32 DO
                TR_CasePass[tI] := 0;
                TR_CaseCheck[tI] := 0;
                TR_CaseNok[tI] := 0;
            END_FOR;
            // the part of the recipe that is the same in every case, for both evaluation instances
            BenchRcp.GateX := TD_GateX;
            BenchRcp.Gate2X := TD_Gate2X;
            BenchRcp.PeakXLo := TD_PeakXLo;
            BenchRcp.PeakXHi := TD_PeakXHi;
            BenchRcp.StepSpan := TD_StepSpan;
            BenchRcp.StopF := TD_StopF;
            BenchRcp.EnvX0 := TD_EnvX0;
            BenchRcp.EnvDx := TD_EnvDx;
            BenchRcp.EnvN := TD_EnvN;
            StationRcp.GateX := TD_GateX;
            StationRcp.Gate2X := TD_Gate2X;
            StationRcp.PeakXLo := TD_PeakXLo;
            StationRcp.PeakXHi := TD_PeakXHi;
            StationRcp.StepSpan := TD_StepSpan;
            StationRcp.StopF := TD_StopF;
            StationRcp.EnvX0 := TD_EnvX0;
            StationRcp.EnvDx := TD_EnvDx;
            StationRcp.EnvN := TD_EnvN;
            FOR tI := 0 TO 63 DO
                BenchRcp.EnvLo[tI] := TD_EnvLo[tI];
                BenchRcp.EnvHi[tI] := TD_EnvHi[tI];
                StationRcp.EnvLo[tI] := TD_EnvLo[tI];
                StationRcp.EnvHi[tI] := TD_EnvHi[tI];
            END_FOR;
            // the station judges with windows + return stroke (mode 3: limits 32..47)
            StationRcp.Mode := 3;
            StationRcp.G1Lo := TD_Lim[32];
            StationRcp.G1Hi := TD_Lim[33];
            StationRcp.MeanLo := TD_Lim[34];
            StationRcp.MeanHi := TD_Lim[35];
            StationRcp.HystLo := TD_Lim[36];
            StationRcp.HystHi := TD_Lim[37];
            StationRcp.RetFMin := TD_Lim[38];
            StationRcp.G2Lo := TD_Lim[39];
            StationRcp.G2Hi := TD_Lim[40];
            StationRcp.PeakFLo := TD_Lim[41];
            StationRcp.PeakFHi := TD_Lim[42];
            StationRcp.PeakXMin := TD_Lim[43];
            StationRcp.PeakXMax := TD_Lim[44];
            StationRcp.StepLo := TD_Lim[45];
            StationRcp.StopXLo := TD_Lim[46];
            StationRcp.StopXHi := TD_Lim[47];
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

    // --- Replay ---
        IF sPhase = 1 THEN
            FOR tI := 1 TO ReplayPerCall DO
                IF NOT sRecord THEN
                    tCurve := TD_CaseCurve[sCase];
                    tMode := TD_CaseMode[sCase];
                    tA := TD_CurveStart[tCurve];
                    tN := TD_CurveNPull[tCurve];
                    CASE sSub OF
                        0:  // limits of the mode of this case, clear the evaluation
                            tB := (tMode - 1) * 16;
                            BenchRcp.Mode := tMode;
                            BenchRcp.G1Lo := TD_Lim[tB];
                            BenchRcp.G1Hi := TD_Lim[tB + 1];
                            BenchRcp.MeanLo := TD_Lim[tB + 2];
                            BenchRcp.MeanHi := TD_Lim[tB + 3];
                            BenchRcp.HystLo := TD_Lim[tB + 4];
                            BenchRcp.HystHi := TD_Lim[tB + 5];
                            BenchRcp.RetFMin := TD_Lim[tB + 6];
                            BenchRcp.G2Lo := TD_Lim[tB + 7];
                            BenchRcp.G2Hi := TD_Lim[tB + 8];
                            BenchRcp.PeakFLo := TD_Lim[tB + 9];
                            BenchRcp.PeakFHi := TD_Lim[tB + 10];
                            BenchRcp.PeakXMin := TD_Lim[tB + 11];
                            BenchRcp.PeakXMax := TD_Lim[tB + 12];
                            BenchRcp.StepLo := TD_Lim[tB + 13];
                            BenchRcp.StopXLo := TD_Lim[tB + 14];
                            BenchRcp.StopXHi := TD_Lim[tB + 15];
                            Eval.Reset := 1;
                            Eval.Sample := 0;
                            Eval.Stroke := 0;
                            Eval.X := 0.0;
                            Eval.F := 0.0;
                            Eval.Finish := 0;
                            AOI_CurveEval(Eval, BenchRcp);
                            sIdx := 0;
                            sSub := 1;
                        1:  // one sample: the pull samples first, then the return samples
                            IF sIdx < tN THEN
                                tStroke := 1;
                            ELSE
                                tStroke := 2;
                            END_IF;
                            Eval.Reset := 0;
                            Eval.Sample := 1;
                            Eval.Stroke := tStroke;
                            Eval.X := TD_X[tA + sIdx];
                            Eval.F := TD_F[tA + sIdx];
                            Eval.Finish := 0;
                            AOI_CurveEval(Eval, BenchRcp);
                            sIdx := sIdx + 1;
                            IF sIdx >= 2 * tN THEN
                                sSub := 2;
                            END_IF;
                        2:  // judge and compare with the expected values
                            Eval.Reset := 0;
                            Eval.Sample := 0;
                            Eval.Stroke := 0;
                            Eval.X := 0.0;
                            Eval.F := 0.0;
                            Eval.Finish := 1;
                            AOI_CurveEval(Eval, BenchRcp);
                            sMeas[0] := Eval.FpG1;
                            sMeas[1] := Eval.FrG1;
                            sMeas[2] := Eval.FMean;
                            sMeas[3] := Eval.FHyst;
                            sMeas[4] := Eval.FpG2;
                            sMeas[5] := Eval.FPeak;
                            sMeas[6] := Eval.XPeak;
                            sMeas[7] := Eval.FStep;
                            sMeas[8] := Eval.XStop;
                            IF Eval.Ok XOR TD_ExpOk[sCase] THEN
                                sCk := 1;
                            ELSIF Eval.NokCode <> TD_ExpNok[sCase] THEN
                                sCk := 2;
                            ELSIF Eval.EnvViol <> TD_ExpEnvViol[sCase] THEN
                                sCk := 12;
                            ELSIF Eval.EnvNodes <> TD_ExpEnvNodes[sCase] THEN
                                sCk := 13;
                            END_IF;
                            FOR tJ := 0 TO 8 DO
                                tB := (sCase - 1) * 9 + tJ;
                                IF TD_ExpFeatValid[tB] THEN
                                    tErr := ABS(sMeas[tJ] - TD_ExpFeat[tB]);
                                    IF tErr > sMaxErr THEN
                                        sMaxErr := tErr;
                                    END_IF;
                                    IF tErr > TD_Tol AND sCk = 0 THEN
                                        sCk := 3 + tJ;
                                    END_IF;
                                END_IF;
                            END_FOR;
                            sNok := Eval.NokCode;
                            sSub := 0;
                            sRecord := 1;
                    END_CASE;
                END_IF;
            END_FOR;
        END_IF;

    // --- Station ---
        IF sPhase = 2 THEN
            FOR tI := 1 TO ScansPerCall DO
                IF sPhase = 2 AND NOT sRecord THEN
                    IF sTim < 30000 THEN
                        sTim := sTim + 1;
                    END_IF;
                    // what the operator and the line do, and what the station must have done by now
                    CASE sStep OF
                        10:  // good LH unit
                            sPart := 1;
                            sLH := 1;
                            sRH := 0;
                            sCurve := TD_GoodCurve;
                            sPlantReset := 1;
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
                                sRecord := 1;
                                sPart := 0;
                                sStep := 12;
                                sTim := 0;
                            END_IF;
                        12:  // unit taken out
                            IF Station.State = 0 OR sTim > 4000 THEN
                                sStep := 20;
                                sTim := 0;
                            END_IF;
                        20:  // RH unit while LH units are built
                            sPart := 1;
                            sLH := 0;
                            sRH := 1;
                            sCurve := TD_GoodCurve;
                            sPlantReset := 1;
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
                                sRecord := 1;
                                sStep := 22;
                                sTim := 0;
                            END_IF;
                        22:  // reject lock: a chute signal while the rejected unit is still in the fixture
                            sChute := sTim >= 5 AND sTim < 10;
                            IF sTim >= 20 THEN
                                IF Station.State <> 8 OR NOT Station.Locked THEN
                                    sCk := 26;
                                END_IF;
                                sPart := 0;
                                sStep := 23;
                                sTim := 0;
                            END_IF;
                        23:  // the unit is taken out and a new good unit is put in without using the chute
                            IF sTim = 20 THEN
                                sPart := 1;
                                sLH := 1;
                                sRH := 0;
                                sPlantReset := 1;
                            END_IF;
                            IF sTim >= 400 THEN
                                IF sCk = 0 AND (Station.State <> 8 OR Station.CntTotal <> 2 OR Plant.Moved) THEN
                                    sCk := 26;
                                END_IF;
                                sPart := 0;
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
                                sRecord := 1;
                                sStep := 30;
                                sTim := 0;
                            END_IF;
                        30:  // LH unit with unhooked latch lever
                            sPart := 1;
                            sLH := 1;
                            sRH := 0;
                            sCurve := TD_BadCurve;
                            sPlantReset := 1;
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
                                sRecord := 1;
                                sPart := 0;
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
                            sPart := 1;
                            sCurve := TD_BadCurve;
                            sPlantReset := 1;
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
                                sPart := 0;
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
                                sPart := 1;
                                sCurve := TD_GoodCurve;
                                sPlantReset := 1;
                                sStep := 43;
                                sTim := 0;
                            END_IF;
                        43:  // the start must stay blocked until the acknowledge
                            IF sTim >= 400 THEN
                                IF sCk = 0 AND (Station.State <> 0 OR Station.CntTotal <> 4 OR Plant.Moved) THEN
                                    sCk := 28;
                                END_IF;
                                sRecord := 1;
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
                                sRecord := 1;
                                sPart := 0;
                                sAck := 0;
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
                    Plant.Reset := sPlantReset;
                    Plant.CycleTime := 0.002;
                    Plant.QVel := Station.QVel;
                    Plant.QDriveEnable := Station.QDriveEnable;
                    Plant.QClamp := Station.QClamp;
                    Plant.PartPresent := sPart;
                    Plant.Curve := sCurve;
                    Plant.Seat := 5.0;
                    AOI_TestPlant(Plant, TD_X, TD_F, TD_CurveStart, TD_CurveNPull);
                    sPlantReset := 0;
                    Station.CycleTime := 0.002;
                    Station.SafetyOk := 1;
                    Station.DriveOk := 1;
                    Station.AckFault := sAck;
                    Station.StartEnable := 1;
                    Station.PartPresent := sPart;
                    Station.SensLH := sPart AND sLH;
                    Station.SensRH := sPart AND sRH;
                    Station.VariantLH := 1;
                    Station.ClampClosed := Plant.ClampClosed;
                    Station.ClampOpen := Plant.ClampOpen;
                    Station.RejectChute := sChute;
                    Station.Pos := Plant.Pos;
                    Station.Force := Plant.Force;
                    Station.Compliance := 0.0;
                    AOI_HandleStation(Station, StationRcp, StationCnt);
                END_IF;
            END_FOR;
        END_IF;

    // --- Record ---
        IF sRecord THEN
            sRun := sRun + 1;
            IF sCk = 0 THEN
                sPassed := sPassed + 1;
                TR_CasePass[sCase] := 1;
            ELSE
                sFailed := sFailed + 1;
                IF sFirstCase = 0 THEN
                    sFirstCase := sCase;
                    sFirstCheck := sCk;
                END_IF;
            END_IF;
            TR_CaseCheck[sCase] := sCk;
            TR_CaseNok[sCase] := sNok;
            sCase := sCase + 1;
            sCk := 0;
            sNok := 0;
            sRecord := 0;
            IF sPhase = 1 AND sCase > TD_NCases THEN
                sPhase := 2;
            END_IF;
        END_IF;

    // --- Result ---
        TR_CasesTotal := TD_NCases + 6;
        TR_CasesRun := sRun;
        TR_CasesPassed := sPassed;
        TR_CasesFailed := sFailed;
        TR_FirstFailedCase := sFirstCase;
        TR_FirstFailedCheck := sFirstCheck;
        TR_MaxFeatError := sMaxErr;
        TR_BenchCalls := sCalls;
        TR_Done := sPhase = 3;
        TR_AllPassed := sPhase = 3 AND sFailed = 0 AND sPassed = TD_NCases + 6;

