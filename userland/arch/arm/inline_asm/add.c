/* 1 + 2 == 3
 *
 * https://cirosantilli.com/linux-kernel-module-cheat#gcc-inline-assembly
 */

#include <assert.h>
#include <inttypes.h>

int main(void) {
    uint32_t in0 = 1, in1 = 2, out;
    __asm__ (
        "add %[out], %[in0], %[in1];"
        : [out] "=r" (out)
        : [in0] "r"  (in0),
          [in1] "r"  (in1)
    );
    assert(in0 == 1);
    assert(in1 == 2);
    assert(out == 3);
}
