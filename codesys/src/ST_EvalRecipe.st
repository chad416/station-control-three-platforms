// Evaluation recipe of FB_CurveEval as one structure. Not in the Siemens original: there the bench
// writes the recipe straight into the multi-instance Station.Eval. CODESYS refuses that
// (C0037 "'Eval' is no input of 'FB_HandleStation'"), so the station takes the recipe by reference
// and copies it into its own evaluation instance when it tares, once per part.
TYPE ST_EvalRecipe :
STRUCT
    Mode : INT := 3;
    GateX : REAL := 3.0;   // mm
    Gate2X : REAL := 10.0;   // mm
    PeakXLo : REAL := 13.0;   // mm
    PeakXHi : REAL := 26.0;   // mm
    StepSpan : REAL := 2.0;   // mm
    StopF : REAL := 30.0;   // N
    G1Lo : REAL;
    G1Hi : REAL;
    MeanLo : REAL;
    MeanHi : REAL;
    HystLo : REAL;
    HystHi : REAL;
    RetFMin : REAL;
    G2Lo : REAL;
    G2Hi : REAL;
    PeakFLo : REAL;
    PeakFHi : REAL;
    PeakXMin : REAL;
    PeakXMax : REAL;
    StepLo : REAL;
    StopXLo : REAL;
    StopXHi : REAL;
    EnvX0 : REAL := 1.0;   // mm
    EnvDx : REAL := 0.5;   // mm
    EnvN : INT := 55;
    EnvLo : ARRAY[0..63] OF REAL;   // N
    EnvHi : ARRAY[0..63] OF REAL;   // N
END_STRUCT
END_TYPE
