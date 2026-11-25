// Result of the test bench (FB_TestBench). Port of DB_TestResult; read by codesys/scripts/build_and_run.py.
{attribute 'qualified_only'}
VAR_GLOBAL
    Done : BOOL;   // the bench has finished; the values below no longer change
    AllPassed : BOOL;   // Done and every case passed
    CasesTotal : INT;
    CasesRun : INT;
    CasesPassed : INT;
    CasesFailed : INT;
    FirstFailedCase : INT;   // 0 = none
    FirstFailedCheck : INT;   // 0 = none; codes in the header of FB_TestBench
    MaxFeatError : REAL;   // N or mm, largest difference of an element from its expected value
    BenchCalls : DINT;   // task cycles the bench needed
    CasePass : ARRAY[1..32] OF BOOL;
    CaseCheck : ARRAY[1..32] OF INT;   // failed check of each case, 0 = passed
    CaseNok : ARRAY[1..32] OF INT;   // NOK code the block gave in each case
END_VAR
