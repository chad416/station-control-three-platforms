// The station on the machine, in the periodic task StationTask (Rate 2 ms).
// The I/O mapping (Station.SafetyOk, Station.Pos, Station.Force ... from the input modules, and the
// outputs QClamp, QVel ... to the output modules) depends on the modules and is not part of this port.
// CycleTime is the time base of every timer in the station: it must equal the task Rate.
Station.CycleTime := 0.002;
AOI_HandleStation(Station, Rcp, CntByCode);
