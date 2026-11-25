// Port of OB1 "Main" with the instance DB "InstTestBench": runs the bench by itself after the start.
PROGRAM PLC_PRG
VAR
    Bench : FB_TestBench;
END_VAR
(* @IMPLEMENTATION *)
Bench();
