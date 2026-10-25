#define _XOPEN_SOURCE 700
#include <signal.h>
#include <unistd.h>

/* Diagnostic candidate for the single-threaded GNAT initializer only.
 * This propagates observed setup failures, not a readiness attestation.
 * No allocation, logging, retry, handler replacement or Ada finalization.
 */
static volatile sig_atomic_t installing_handler;

void __real___gnat_install_handler(void);
void __wrap___gnat_install_handler(void);
int __real_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact);
int __wrap_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact);
int __real_sigaltstack(const stack_t *stack, stack_t *oldstack);
int __wrap_sigaltstack(const stack_t *stack, stack_t *oldstack);
int __real_sigemptyset(sigset_t *set);
int __wrap_sigemptyset(sigset_t *set);

void __wrap___gnat_install_handler(void)
{
    installing_handler = 1;
    __real___gnat_install_handler();
    installing_handler = 0;
}

static int checked_result(int result)
{
    if (result == -1 && installing_handler != 0) {
        _exit(74);
    }
    return result;
}

int __wrap_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact)
{
    return checked_result(__real_sigaction(sig, act, oldact));
}

int __wrap_sigaltstack(const stack_t *stack, stack_t *oldstack)
{
    return checked_result(__real_sigaltstack(stack, oldstack));
}

int __wrap_sigemptyset(sigset_t *set)
{
    return checked_result(__real_sigemptyset(set));
}
