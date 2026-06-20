program stencil_driver
  use iso_fortran_env, only: int64, real64
  use ieee_arithmetic, only: ieee_is_finite
  use candidate_kernel, only: kernel
  use reference_kernel, only: reference
  implicit none

  character(len=32) :: mode
  integer :: n, repetitions, seed

  call get_command_argument(1, mode)
  n = read_int_arg(2, 4099)
  repetitions = read_int_arg(3, 1)
  seed = read_int_arg(4, 101)

  select case (trim(mode))
  case ("verify")
    call run_verify(n, seed)
  case ("bench")
    call run_benchmark(n, repetitions, seed)
  case default
    error stop "unknown driver mode"
  end select

contains

  integer function read_int_arg(position, default_value) result(value)
    integer, intent(in) :: position, default_value
    character(len=64) :: raw
    integer :: status

    call get_command_argument(position, raw)
    if (len_trim(raw) == 0) then
      value = default_value
      return
    end if

    read (raw, *, iostat=status) value
    if (status /= 0) value = default_value
  end function read_int_arg

  subroutine fill_input(n, seed, x)
    integer, intent(in) :: n, seed
    real(real64), intent(out) :: x(n)
    integer :: i
    real(real64) :: phase

    do i = 1, n
      phase = real(i + seed, real64)
      x(i) = sin(0.013_real64 * phase) + 0.125_real64 * cos(0.031_real64 * phase)
    end do
  end subroutine fill_input

  subroutine run_verify(n, seed)
    integer, intent(in) :: n, seed
    real(real64), allocatable :: x(:), x_original(:), x_reference(:), y(:), expected(:)
    real(real64) :: max_abs_error, max_rel_error, denom
    integer :: finite_flag, input_unchanged, correct

    allocate (x(n), x_original(n), x_reference(n), y(n), expected(n))
    call fill_input(n, seed, x)
    x_original = x
    x_reference = x
    call reference(n, x_reference, expected)
    call kernel(n, x, y)

    max_abs_error = maxval(abs(y - expected))
    denom = max(1.0e-30_real64, maxval(abs(expected)))
    max_rel_error = max_abs_error / denom
    finite_flag = merge(1, 0, all(ieee_is_finite(y)))
    input_unchanged = merge(1, 0, all(x == x_original))
    correct = merge(1, 0, finite_flag == 1 .and. max_abs_error <= 1.0e-11_real64 &
         .and. max_rel_error <= 1.0e-11_real64 .and. input_unchanged == 1)

    write (*, '(A,I0)') "correct=", correct
    write (*, '(A,I0)') "finite=", finite_flag
    write (*, '(A,I0)') "input_unchanged=", input_unchanged
    write (*, '(A,ES26.16)') "max_abs_error=", max_abs_error
    write (*, '(A,ES26.16)') "max_rel_error=", max_rel_error
  end subroutine run_verify

  subroutine run_benchmark(n, repetitions, seed)
    integer, intent(in) :: n, repetitions, seed
    real(real64), allocatable :: x_candidate(:), x_original(:), x_reference(:), y(:), expected(:)
    integer(int64) :: start_count, end_count, count_rate
    integer :: iteration, finite_flag, input_unchanged, correct
    integer :: reference_input_unchanged
    real(real64) :: candidate_time_s, reference_time_s, max_abs_error, max_rel_error, denom
    real(real64) :: candidate_checksum, reference_checksum, checksum_abs_error
    real(real64) :: checksum_rel_error, checksum_denom

    allocate (x_candidate(n), x_original(n), x_reference(n), y(n), expected(n))
    candidate_checksum = 0.0_real64
    reference_checksum = 0.0_real64
    finite_flag = 1
    input_unchanged = 1

    call system_clock(start_count, count_rate)
    do iteration = 1, repetitions
      call fill_input(n, seed + 7919 * iteration, x_candidate)
      x_original = x_candidate
      y = -1234567.0_real64
      call kernel(n, x_candidate, y)
      candidate_checksum = candidate_checksum + sum(y)
      if (.not. all(ieee_is_finite(y))) finite_flag = 0
      if (.not. all(x_candidate == x_original)) input_unchanged = 0
    end do
    call system_clock(end_count)
    candidate_time_s = real(end_count - start_count, real64) / real(count_rate, real64)

    reference_input_unchanged = 1
    call system_clock(start_count, count_rate)
    do iteration = 1, repetitions
      call fill_input(n, seed + 7919 * iteration, x_reference)
      x_original = x_reference
      call reference(n, x_reference, expected)
      reference_checksum = reference_checksum + sum(expected)
      if (.not. all(x_reference == x_original)) reference_input_unchanged = 0
    end do
    call system_clock(end_count)
    reference_time_s = real(end_count - start_count, real64) / real(count_rate, real64)

    call fill_input(n, seed + 7919 * repetitions, x_reference)
    call reference(n, x_reference, expected)
    max_abs_error = maxval(abs(y - expected))
    denom = max(1.0e-30_real64, maxval(abs(expected)))
    max_rel_error = max_abs_error / denom
    checksum_abs_error = abs(candidate_checksum - reference_checksum)
    checksum_denom = max(1.0_real64, abs(reference_checksum))
    checksum_rel_error = checksum_abs_error / checksum_denom
    correct = merge(1, 0, finite_flag == 1 .and. max_abs_error <= 1.0e-11_real64 &
         .and. max_rel_error <= 1.0e-11_real64 .and. input_unchanged == 1 &
         .and. reference_input_unchanged == 1 .and. checksum_rel_error <= 1.0e-10_real64)

    write (*, '(A,ES26.16)') "candidate_time_s=", candidate_time_s
    write (*, '(A,ES26.16)') "reference_time_s=", reference_time_s
    write (*, '(A,ES26.16)') "candidate_checksum=", candidate_checksum
    write (*, '(A,ES26.16)') "reference_checksum=", reference_checksum
    write (*, '(A,I0)') "correct=", correct
    write (*, '(A,I0)') "finite=", finite_flag
    write (*, '(A,I0)') "input_unchanged=", input_unchanged
    write (*, '(A,ES26.16)') "max_abs_error=", max_abs_error
    write (*, '(A,ES26.16)') "max_rel_error=", max_rel_error
  end subroutine run_benchmark

end program stencil_driver
