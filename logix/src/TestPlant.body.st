
    // --- Part ---
        IF Reset THEN
            sReturn := 0;
            sK := 0;
            sMoved := 0;
        END_IF;

    // --- AxisAndClamp ---
        IF QDriveEnable THEN
            sPos := sPos + QVel * CycleTime;
            IF QVel <> 0.0 THEN
                sMoved := 1;
            END_IF;
        END_IF;
        IF sPos < 0.0 THEN
            sPos := 0.0;
        END_IF;
        IF QClamp THEN
            sClamp := sClamp + CycleTime;
            sMoved := 1;
        ELSE
            sClamp := sClamp - CycleTime;
        END_IF;
        IF sClamp < 0.0 THEN
            sClamp := 0.0;
        ELSIF sClamp > 0.25 THEN
            sClamp := 0.25;
        END_IF;

    // --- Handle ---
        tX := sPos - Seat;
        tF := 0.0;
        tA := CurveStart[Curve];
        tN := CurveNPull[Curve];
        IF QVel < 0.0 AND NOT sReturn THEN
            sReturn := 1;
            sK := 0;
        END_IF;
        IF PartPresent AND tX >= 0.0 AND tN >= 2 THEN
            IF sReturn THEN
                tA := tA + tN;   // the return samples follow the pull samples; their travel falls
            END_IF;
            // move on to the pair of samples around the travel (the axis moves less than 8 samples per call)
            FOR tI := 1 TO 8 DO
                IF sK < tN - 2 THEN
                    IF NOT sReturn AND X[tA + sK + 1] < tX THEN
                        sK := sK + 1;
                    ELSIF sReturn AND X[tA + sK + 1] > tX THEN
                        sK := sK + 1;
                    END_IF;
                END_IF;
            END_FOR;
            tX0 := X[tA + sK];
            tX1 := X[tA + sK + 1];
            tF0 := F[tA + sK];
            tF1 := F[tA + sK + 1];
            IF NOT sReturn THEN
                IF tX >= tX1 THEN
                    tF := tF1 + (tX - tX1) * 25.0;
                ELSIF tX <= tX0 OR tX1 - tX0 < 0.000001 THEN
                    tF := tF0;
                ELSE
                    tF := tF0 + (tF1 - tF0) * (tX - tX0) / (tX1 - tX0);
                END_IF;
            ELSE
                IF tX >= tX0 THEN
                    tF := tF0 + (tX - tX0) * 25.0;
                ELSIF tX <= tX1 OR tX0 - tX1 < 0.000001 THEN
                    tF := tF1;
                ELSE
                    tF := tF1 + (tF0 - tF1) * (tX - tX1) / (tX0 - tX1);
                END_IF;
            END_IF;
        END_IF;

    // --- Outputs ---
        Pos := sPos;
        Force := tF;
        ClampClosed := sClamp >= 0.25;
        ClampOpen := sClamp <= 0.0;
        Moved := sMoved;

