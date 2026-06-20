# Local KIM KDM6 Run Cases

This directory is for copied local KIM-meso run bundles only. Its contents are
ignored by Git because they may contain large NetCDF files, host-specific
executables, local paths, and private run logs.

Recommended local bundle name:

```text
mp37_quarter_ss/
```

The bundle should contain only `mp_physics=37` Fortran KDM6 evidence:

```text
main/wrf.exe
main/ideal.exe
run/namelist.input
run/input_sounding
run/wrfinput_d01
reference/wrfout.37.quarter_ss.nc
logs/compile_quarter_ss.log
```

Run from the copied bundle with:

```bash
cd science-codeevolve/problems/kim_kdm6_microphysics/input/local_run_cases/mp37_quarter_ss/run
mpirun -np 1 ./wrf.exe
```

If the copied host binary crashes while appending frequent history output, a
short smoke run can use a larger `history_interval` while preserving
`mp_physics=37`. Treat that as an execution smoke test only, not as the final
baseline evidence for CodeEvolve fitness.

Do not use `mp_physics=137`, KDM6AD, LibTorch wrapper, C ABI, VJP/JVP, or AD
runtime outputs as evidence for this problem. If the copied executable is linked
against LibTorch because of the host build, treat that as a host build artifact,
not as a valid CodeEvolve target path.

For a baseline receipt, include both success logs and diagnostic logs such as
`rsl.error.0000`. The verifier rejects `mp_physics=137`, `mp=137`, and
`KDM6AD_PHASE` markers in any configured run or diagnostic log.
