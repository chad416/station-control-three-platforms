
    // --- Inputs ---
        FNet := Force - sTare;
        tChuteEdge := RejectChute AND NOT sChutePrev;
        sChutePrev := RejectChute;
        sTim := sTim + CycleTime;
        sTCycle := sTCycle + CycleTime;
        QVel := 0.0;
        // exactly the sensor of the expected hand, and not the other one
        tVariantOk := (VariantLH AND SensLH AND NOT SensRH) OR (NOT VariantLH AND SensRH AND NOT SensLH);

    // --- Faults ---
        IF sState <> 9 AND (NOT SafetyOk OR NOT DriveOk) THEN
            IF NOT SafetyOk THEN
                FaultCode := 1;
            ELSE
                FaultCode := 2;
            END_IF;
            IF sState <> 10 THEN
                sInTest := sState >= 1 AND sState <= 6;
                sWasLocked := sState = 8;
            END_IF;
            sState := 9;
        END_IF;

    // --- Sequence ---
        CASE sState OF
            0:  // Idle
                Locked := 0;
                IF NOT PartPresent THEN
                    sTim := 0.0;
                    QLampOk := 0;
                    QLampNok := 0;
                ELSIF sTim >= TPresent AND StartEnable AND ClampOpen AND NOT sRigCheckRequired THEN
                    Verdict := 0;
                    NokCode := 0;
                    sPreNok := 0;
                    sTCycle := 0.0;
                    sTim := 0.0;
                    IF tVariantOk THEN
                        sState := 1;
                    ELSE
                        sPreNok := 20;   // never pull a part of the wrong hand
                        sState := 6;
                    END_IF;
                END_IF;
            1:  // Clamp
                QClamp := 1;
                IF ClampClosed THEN
                    sTim := 0.0;
                    sState := 2;
                ELSIF sTim > TClampMax THEN
                    FaultCode := 3;
                    sInTest := 1;
                    sState := 9;
                END_IF;
            2:  // Tare
                IF sTim >= 0.05 THEN
                    IF ABS(Force) > TareTol THEN
                        FaultCode := 4;
                        sInTest := 1;
                        sState := 9;
                    ELSE
                        sTare := Force;
                        COP(Rcp, sRcp, 1);   // the recipe of this part
                        Eval.Reset := 1;
                        Eval.Sample := 0;
                        Eval.Stroke := 0;
                        Eval.X := 0.0;
                        Eval.F := 0.0;
                        Eval.Finish := 0;
                        AOI_CurveEval(Eval, sRcp);
                        sState := 3;
                    END_IF;
                END_IF;
            3:  // Approach
                QVel := VPull;
                IF FNet > FTouch THEN
                    sTouchPos := Pos;
                    sFTouch := FNet;
                    IF Pos < TouchLo OR Pos > TouchHi THEN
                        sPreNok := 21;
                        sState := 5;
                    ELSE
                        XTravel := 0.0;
                        Eval.Reset := 0;
                        Eval.Sample := 1;
                        Eval.Stroke := 1;
                        Eval.X := 0.0;
                        Eval.F := FNet;
                        Eval.Finish := 0;
                        AOI_CurveEval(Eval, sRcp);
                        sState := 4;
                    END_IF;
                ELSIF Pos > TouchHi THEN
                    sPreNok := 21;
                    sTouchPos := Pos;
                    sFTouch := 0.0;
                    sState := 5;
                END_IF;
            4:  // Pull
                QVel := VPull;
                XTravel := Pos - sTouchPos - (FNet - sFTouch) * Compliance;
                Eval.Reset := 0;
                Eval.Sample := 1;
                Eval.Stroke := 1;
                Eval.X := XTravel;
                Eval.F := FNet;
                Eval.Finish := 0;
                AOI_CurveEval(Eval, sRcp);
                IF FNet >= FAbsMax THEN
                    sPreNok := 22;
                    sState := 5;
                ELSIF FNet >= FRev THEN
                    sState := 5;
                ELSIF XTravel >= XMax THEN
                    sPreNok := 23;
                    sState := 5;
                END_IF;
            5:  // Return
                XTravel := Pos - sTouchPos - (FNet - sFTouch) * Compliance;
                IF Pos > sTouchPos - 0.5 THEN
                    QVel := -VPull;
                    IF sPreNok = 0 THEN
                        Eval.Reset := 0;
                        Eval.Sample := 1;
                        Eval.Stroke := 2;
                        Eval.X := XTravel;
                        Eval.F := FNet;
                        Eval.Finish := 0;
                        AOI_CurveEval(Eval, sRcp);
                    END_IF;
                ELSIF Pos > 0.05 THEN
                    QVel := -VHome;
                ELSE
                    sState := 6;
                END_IF;
            6:  // Evaluate
                IF sPreNok <> 0 THEN
                    tCode := sPreNok;
                ELSE
                    Eval.Reset := 0;
                    Eval.Sample := 0;
                    Eval.Stroke := 0;
                    Eval.X := 0.0;
                    Eval.F := 0.0;
                    Eval.Finish := 1;
                    AOI_CurveEval(Eval, sRcp);
                    tCode := Eval.NokCode;
                END_IF;
                NokCode := tCode;
                TCycle := sTCycle;
                sCntTotal := sCntTotal + 1;
                sCntByCode[tCode] := sCntByCode[tCode] + 1;
                QClamp := 0;
                sTim := 0.0;
                IF tCode = 0 THEN
                    Verdict := 1;
                    sCntOk := sCntOk + 1;
                    sCntConsecNok := 0;
                    QLampOk := 1;
                    sState := 7;
                ELSE
                    Verdict := 2;
                    sCntNok := sCntNok + 1;
                    sCntConsecNok := sCntConsecNok + 1;
                    QLampNok := 1;
                    sPartGone := 0;
                    sState := 8;
                END_IF;
            7:  // UnloadOk
                QClamp := 0;
                IF NOT PartPresent AND ClampOpen THEN
                    sTim := 0.0;
                    sState := 0;
                END_IF;
            8:  // RejectLock
                QClamp := 0;
                Locked := 1;
                IF NOT PartPresent THEN
                    sPartGone := 1;
                END_IF;
                QCallOperator := sTim > TRejectWarn OR sRigCheckRequired;
                IF sPartGone AND tChuteEdge THEN
                    sCntRejectConfirmed := sCntRejectConfirmed + 1;
                    sRigCheckRequired := sCntConsecNok >= MaxConsecNok;
                    QCallOperator := sRigCheckRequired;
                    Locked := 0;
                    sTim := 0.0;
                    sState := 0;
                END_IF;
            9:  // Fault
                QClamp := sInTest;
                QCallOperator := 1;
                IF AckFault AND SafetyOk AND DriveOk THEN
                    FaultCode := 0;
                    QCallOperator := 0;
                    sState := 10;
                END_IF;
            10:  // Home
                IF Pos > 0.05 THEN
                    QVel := -VPull;
                ELSIF sInTest THEN
                    sInTest := 0;
                    sPreNok := 24;
                    sState := 6;
                ELSIF sWasLocked THEN
                    sWasLocked := 0;   // a fault does not release the reject lock
                    sState := 8;
                ELSE
                    sState := 0;
                END_IF;
            ELSE
                sState := 9;
        END_CASE;

    // --- RigCheck ---
        // the lock after too many rejects in a row is released by the acknowledge key
        IF sRigCheckRequired AND AckFault AND sState = 0 THEN
            sRigCheckRequired := 0;
            sCntConsecNok := 0;
            QCallOperator := 0;
        END_IF;
        QDriveEnable := SafetyOk AND DriveOk AND sState <> 9;

    // --- Outputs ---
        // state and counters live in static variables; these outputs are written here and nowhere else
        State := sState;
        RigCheckRequired := sRigCheckRequired;
        CntTotal := sCntTotal;
        CntOk := sCntOk;
        CntNok := sCntNok;
        CntRejectConfirmed := sCntRejectConfirmed;
        CntConsecNok := sCntConsecNok;
        COP(sCntByCode[0], CntByCode[0], 32);   // InOut array: Logix allows no array outputs

        // the curve elements of the last part for the operator screen: the local tag Eval cannot be
        // read from outside the AOI (Siemens and CODESYS screens read Station.Eval directly)
        E_FpG1 := Eval.FpG1;
        E_FrG1 := Eval.FrG1;
        E_FMean := Eval.FMean;
        E_FHyst := Eval.FHyst;
        E_FpG2 := Eval.FpG2;
        E_FPeak := Eval.FPeak;
        E_XPeak := Eval.XPeak;
        E_FStep := Eval.FStep;
        E_XStop := Eval.XStop;
