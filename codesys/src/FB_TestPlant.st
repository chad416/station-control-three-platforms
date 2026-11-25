FUNCTION_BLOCK FB_TestPlant
//  CODESYS V3.5 port of the Siemens SCL block. Only the syntax changed: no # before local names,
//  REGION as {region} pragma, global data as qualified GVL names, LIMIT with positional arguments.
//  Not part of the station program. Used by FB_TestBench so that FB_HandleStation can run in the
//  PLC without hardware.
//    axis     position follows the speed command, no dynamics
//    clamp    closed 0.25 s after the command, open 0.25 s after it is taken away
//    handle   force read from a recorded curve in DB_TestData at the travel Pos - Seat:
//             the pull samples until the speed command turns negative, the return samples after
//             that; linear between samples; past the last pull sample the end stop goes on at
//             25 N/mm. The recorded travel has the rig deflection taken out already, so the
//             station is run with Compliance = 0.
   VAR_INPUT
      Reset : Bool;   // a new part is in the fixture
      CycleTime : Real := 0.002;   // s
      QVel : Real;   // mm/s
      QDriveEnable : Bool;
      QClamp : Bool;
      PartPresent : Bool;
      Curve : Int;   // recorded curve the part follows
      Seat : Real := 5.0;   // mm, axis position at which the hook meets the grip
   END_VAR

   VAR_OUTPUT
      Pos : Real;   // mm
      Force : Real;   // N
      ClampClosed : Bool;
      ClampOpen : Bool;
      Moved : Bool;   // the axis has moved or the clamp has closed since the last Reset
   END_VAR

   VAR
      sPos : Real;
      sClamp : Real;
      sReturn : Bool;
      sK : Int;
      sMoved : Bool;
   END_VAR

   VAR_TEMP
      tI : Int;
      tA : Int;
      tN : Int;
      tX : Real;
      tF : Real;
      tX0 : Real;
      tX1 : Real;
      tF0 : Real;
      tF1 : Real;
   END_VAR

(* @IMPLEMENTATION *)
    {region "Part"}
        IF Reset THEN
            sReturn := FALSE;
            sK := 0;
            sMoved := FALSE;
        END_IF;
    {endregion}

    {region "AxisAndClamp"}
        IF QDriveEnable THEN
            sPos := sPos + QVel * CycleTime;
            IF QVel <> 0.0 THEN
                sMoved := TRUE;
            END_IF;
        END_IF;
        IF sPos < 0.0 THEN
            sPos := 0.0;
        END_IF;
        IF QClamp THEN
            sClamp := sClamp + CycleTime;
            sMoved := TRUE;
        ELSE
            sClamp := sClamp - CycleTime;
        END_IF;
        sClamp := LIMIT(0.0, sClamp, 0.25);
    {endregion}

    {region "Handle"}
        tX := sPos - Seat;
        tF := 0.0;
        tA := GVL_TestData.CurveStart[Curve];
        tN := GVL_TestData.CurveNPull[Curve];
        IF QVel < 0.0 AND NOT sReturn THEN
            sReturn := TRUE;
            sK := 0;
        END_IF;
        IF PartPresent AND tX >= 0.0 AND tN >= 2 THEN
            IF sReturn THEN
                tA := tA + tN;   // the return samples follow the pull samples; their travel falls
            END_IF;
            // move on to the pair of samples around the travel (the axis moves less than 8 samples per call)
            FOR tI := 1 TO 8 DO
                IF sK < tN - 2 THEN
                    IF NOT sReturn AND GVL_TestData.X[tA + sK + 1] < tX THEN
                        sK := sK + 1;
                    ELSIF sReturn AND GVL_TestData.X[tA + sK + 1] > tX THEN
                        sK := sK + 1;
                    END_IF;
                END_IF;
            END_FOR;
            tX0 := GVL_TestData.X[tA + sK];
            tX1 := GVL_TestData.X[tA + sK + 1];
            tF0 := GVL_TestData.F[tA + sK];
            tF1 := GVL_TestData.F[tA + sK + 1];
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
    {endregion}

    {region "Outputs"}
        Pos := sPos;
        Force := tF;
        ClampClosed := sClamp >= 0.25;
        ClampOpen := sClamp <= 0.0;
        Moved := sMoved;
    {endregion}
END_FUNCTION_BLOCK
