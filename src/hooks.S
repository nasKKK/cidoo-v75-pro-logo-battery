@ Hooks into the factory firmware. Each .hook_XXXX section is placed at address 0xXXXX by patch.ld
@ and overwrites the factory instruction there; build.py checks the bytes it replaces.

	.code 16

@ Factory functions called by logo.c, marked as TC32 (Thumb-like) code so that the linker
@ calls them with a plain tjl and adds no ARM interworking veneer.
	.global	fw_logo_static, fw_logo_led, fw_key_led
	.thumb_set	fw_logo_static, 0xb348
	.thumb_set	fw_logo_led, 0x9030
	.thumb_set	fw_key_led, 0x8fbc

@ 0xb41c: "tjl 0xb348" (logo mode 3, static colour) -> logo_normal; the next instruction pops pc.
	.section .hook_b41c, "ax"
	tjl	logo_normal

@ 0xb66e: low battery branch after the LED buffers were cleared -> low_entry, no return.
	.section .hook_b66e, "ax"
	tjl	low_entry

@ 0xb558: low battery branch, "tloadr r2,[pc,#604]; tloadrb r1,[r2,#0]" (r2 = 0x847258, the refresh
@ counter) -> low_fast_entry, which does the same loads and returns to 0xb55c.
	.section .hook_b558, "ax"
	tjl	low_fast_entry

@ low_fast_entry: logo_low_fast, keeping r0 and r3 (r3 is stored into the counter at 0xb658).
	.section .text.low_fast_entry, "ax"
	.align	2
	.global	low_fast_entry
	.thumb_func
low_fast_entry:
	tpush	{r0, r3, lr}
	tjl	logo_low_fast
	tpop	{r0, r3}
	tloadr	r2, .L_count
	tloadrb	r1, [r2, #0]
	tpop	{pc}
	.align	2
.L_count:
	.word	0x00847258

@ low_entry: logo_low, then back into the factory function at 0xb57a with r4 = 0x847230
@ (r5 and r6 are callee-saved by logo_low; 0xb57a reloads r5 itself).
	.section .text.low_entry, "ax"
	.align	2
	.global	low_entry
	.thumb_func
low_entry:
	tjl	logo_low
	tloadr	r4, .L_flags
	tloadr	r3, .L_back
	tmov	pc, r3
	.align	2
.L_flags:
	.word	0x00847230
.L_back:
	.word	0x0000b57a
