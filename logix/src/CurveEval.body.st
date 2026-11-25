
    // --- Reset ---
        IF Reset THEN
            sFpG1 := 0.0;
            sFrG1 := 0.0;
            sFMean := 0.0;
            sFHyst := 0.0;
            sFpG2 := 0.0;
            sFPeak := 0.0;
            sXPeak := 0.0;
            sFStep := 0.0;
            sXStop := 0.0;
            sEnvViol := 0;
            sEnvNodes := 0;
            sNSamples := 0;
            sDone := 0;
            sOk := 0;
            sNokCode := 0;
            sHavePrev := 0;
            sGotG1 := 0;
            sGotG2 := 0;
            sGotR1 := 0;
            sGotPeak := 0;
            sGotStop := 0;
            sFMin := 0.0;
        END_IF;

    // --- PullStroke ---
        IF NOT Reset AND Sample AND NOT sDone AND Stroke = 1 THEN
            IF sHavePrev AND sPrevStroke = 1 THEN
                // gates: force at a set travel, linear between the two samples around it
                IF NOT sGotG1 AND sPrevX < Rcp.GateX AND X >= Rcp.GateX THEN
                    sFpG1 := sPrevF + (F - sPrevF) * (Rcp.GateX - sPrevX) / (X - sPrevX);
                    sGotG1 := 1;
                END_IF;
                IF NOT sGotG2 AND sPrevX < Rcp.Gate2X AND X >= Rcp.Gate2X THEN
                    sFpG2 := sPrevF + (F - sPrevF) * (Rcp.Gate2X - sPrevX) / (X - sPrevX);
                    sGotG2 := 1;
                END_IF;
                // end stop: travel at a set force
                IF NOT sGotStop AND sPrevX > Rcp.Gate2X AND sPrevF < Rcp.StopF AND F >= Rcp.StopF THEN
                    sXStop := sPrevX + (X - sPrevX) * (Rcp.StopF - sPrevF) / (F - sPrevF);
                    sGotStop := 1;
                END_IF;
                // envelope: at most four nodes can lie between two samples
                FOR tI := 1 TO 4 DO
                    tNodeX := Rcp.EnvX0 + Rcp.EnvDx * sEnvNodes;
                    IF sEnvNodes < Rcp.EnvN AND sPrevX < tNodeX AND X >= tNodeX THEN
                        tFn := sPrevF + (F - sPrevF) * (tNodeX - sPrevX) / (X - sPrevX);
                        IF tFn < Rcp.EnvLo[sEnvNodes] OR tFn > Rcp.EnvHi[sEnvNodes] THEN
                            sEnvViol := sEnvViol + 1;
                        END_IF;
                        sEnvNodes := sEnvNodes + 1;
                    END_IF;
                END_FOR;
            END_IF;
            // latch release: peak inside the window, then the drop after it
            IF X >= Rcp.PeakXLo AND X <= Rcp.PeakXHi AND (NOT sGotPeak OR F > sFPeak) THEN
                sFPeak := F;
                sXPeak := X;
                sFMin := F;
                sGotPeak := 1;
            ELSIF sGotPeak AND X <= sXPeak + Rcp.StepSpan AND F < sFMin THEN
                sFMin := F;
            END_IF;
            IF sGotPeak THEN
                sFStep := sFPeak - sFMin;
            END_IF;
        END_IF;

    // --- ReturnStroke ---
        IF NOT Reset AND Sample AND NOT sDone AND Stroke = 2 AND sHavePrev THEN
            IF NOT sGotR1 AND sPrevX > Rcp.GateX AND X <= Rcp.GateX THEN
                sFrG1 := sPrevF + (F - sPrevF) * (Rcp.GateX - sPrevX) / (X - sPrevX);
                sGotR1 := 1;
            END_IF;
        END_IF;

    // --- Bookkeeping ---
        IF NOT Reset AND Sample AND NOT sDone THEN
            sPrevX := X;
            sPrevF := F;
            sPrevStroke := Stroke;
            sHavePrev := 1;
            IF sNSamples < 32000 THEN
                sNSamples := sNSamples + 1;
            END_IF;
        END_IF;

    // --- Verdict ---
        IF NOT Reset AND Finish AND NOT sDone THEN
            sFMean := (sFpG1 + sFrG1) * 0.5;
            sFHyst := sFpG1 - sFrG1;
            tCode := 0;
            CASE Rcp.Mode OF
                1:  // peak force only
                    IF NOT sGotPeak THEN
                        tCode := 1;
                    ELSIF sFPeak < Rcp.PeakFLo OR sFPeak > Rcp.PeakFHi THEN
                        tCode := 6;
                    END_IF;
                2, 3:  // windows; mode 3 judges gate 1 with the return stroke
                    IF NOT (sGotG1 AND sGotG2 AND sGotPeak AND sGotStop) THEN
                        tCode := 1;
                    ELSIF Rcp.Mode = 3 AND NOT sGotR1 THEN
                        tCode := 1;
                    ELSIF Rcp.Mode = 2 AND (sFpG1 < Rcp.G1Lo OR sFpG1 > Rcp.G1Hi) THEN
                        tCode := 2;
                    ELSIF Rcp.Mode = 3 AND (sFMean < Rcp.MeanLo OR sFMean > Rcp.MeanHi) THEN
                        tCode := 2;
                    ELSIF Rcp.Mode = 3 AND (sFHyst < Rcp.HystLo OR sFHyst > Rcp.HystHi) THEN
                        tCode := 3;
                    ELSIF Rcp.Mode = 3 AND sFrG1 < Rcp.RetFMin THEN
                        tCode := 4;
                    ELSIF sFpG2 < Rcp.G2Lo OR sFpG2 > Rcp.G2Hi THEN
                        tCode := 5;
                    ELSIF sFPeak < Rcp.PeakFLo OR sFPeak > Rcp.PeakFHi THEN
                        tCode := 6;
                    ELSIF sXPeak < Rcp.PeakXMin OR sXPeak > Rcp.PeakXMax THEN
                        tCode := 7;
                    ELSIF sFStep < Rcp.StepLo THEN
                        tCode := 8;
                    ELSIF sXStop < Rcp.StopXLo OR sXStop > Rcp.StopXHi THEN
                        tCode := 9;
                    END_IF;
                4:  // envelope: every node reached and inside
                    IF sEnvNodes < Rcp.EnvN THEN
                        tCode := 1;
                    ELSIF sEnvViol > 0 THEN
                        tCode := 10;
                    END_IF;
                ELSE
                    tCode := 1;
            END_CASE;
            sNokCode := tCode;
            sOk := tCode = 0;
            sDone := 1;
        END_IF;

    // --- Outputs ---
        // the working values live in static variables; the outputs are written here and nowhere else
        FpG1 := sFpG1;
        FrG1 := sFrG1;
        FMean := sFMean;
        FHyst := sFHyst;
        FpG2 := sFpG2;
        FPeak := sFPeak;
        XPeak := sXPeak;
        FStep := sFStep;
        XStop := sXStop;
        EnvViol := sEnvViol;
        EnvNodes := sEnvNodes;
        NSamples := sNSamples;
        Done := sDone;
        Ok := sOk;
        NokCode := sNokCode;

