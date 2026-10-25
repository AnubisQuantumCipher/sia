#define _XOPEN_SOURCE 700
#include <errno.h>
#include <signal.h>
#include <unistd.h>

void __wrap___gnat_install_handler(void);
int __wrap_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact);
int __wrap_sigaltstack(const stack_t *stack, stack_t *oldstack);
int __wrap_sigemptyset(sigset_t *set);
void __real___gnat_install_handler(void);
int __real_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact);
int __real_sigaltstack(const stack_t *stack, stack_t *oldstack);
int __real_sigemptyset(sigset_t *set);

static struct sigaction action, oldaction;
static stack_t stack, oldstack;
static sigset_t signals;
static char failure;
static unsigned int calls;

static int result_for(char kind)
{
    calls += 1U;
    errno = EACCES;
    return failure == kind ? -1 : 0;
}

int __real_sigaction(int sig, const struct sigaction *act,
                     struct sigaction *oldact)
{
    if (sig != SIGSEGV || act != &action || oldact != &oldaction) {
        _exit(97);
    }
    return result_for('a');
}

int __real_sigaltstack(const stack_t *current, stack_t *old)
{
    if (current != &stack || old != &oldstack) {
        _exit(97);
    }
    return result_for('b');
}

int __real_sigemptyset(sigset_t *set)
{
    if (set != &signals) {
        _exit(97);
    }
    return result_for('e');
}

static void require_success(int value)
{
    if (value != 0 || errno != EACCES) {
        _exit(98);
    }
}

void __real___gnat_install_handler(void)
{
    require_success(__wrap_sigemptyset(&signals));
    require_success(__wrap_sigaction(SIGSEGV, &action, &oldaction));
    require_success(__wrap_sigaltstack(&stack, &oldstack));
}

static int outside_failure(char kind)
{
    failure = kind;
    if (kind == 'a') {
        return __wrap_sigaction(SIGSEGV, &action, &oldaction);
    }
    if (kind == 'b') {
        return __wrap_sigaltstack(&stack, &oldstack);
    }
    return __wrap_sigemptyset(&signals);
}

int main(int argc, char **argv)
{
    if (argc != 2 || argv[1][0] == '\0' || argv[1][1] != '\0') {
        return 96;
    }
    if (argv[1][0] != 's' && argv[1][0] != 'x') {
        failure = argv[1][0];
    }
    __wrap___gnat_install_handler();
    if (calls != 3U || errno != EACCES) {
        return 95;
    }
    if (argv[1][0] == 'x') {
        if (outside_failure('a') != -1 || errno != EACCES
            || outside_failure('b') != -1 || errno != EACCES
            || outside_failure('e') != -1 || errno != EACCES
            || calls != 6U) {
            return 94;
        }
    }
    return 0;
}
