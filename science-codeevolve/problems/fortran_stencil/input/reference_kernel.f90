module reference_kernel
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: reference
contains

  subroutine reference(n, x, y)
    integer, intent(in) :: n
    real(real64), intent(in) :: x(n)
    real(real64), intent(out) :: y(n)
    integer :: i

    y(1) = x(1)

    do i = 2, n - 1
      y(i) = 0.25_real64 * x(i - 1) &
           + 0.50_real64 * x(i)     &
           + 0.25_real64 * x(i + 1)
    end do

    y(n) = x(n)
  end subroutine reference

end module reference_kernel
