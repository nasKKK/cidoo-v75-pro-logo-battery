/* Layout of the patch: hooks at their factory addresses, new code after the end of the factory image. */

SECTIONS
{
	.hook_b41c 0xb41c : { KEEP(*(.hook_b41c)) }
	.hook_b66e 0xb66e : { KEEP(*(.hook_b66e)) }
	.hook_b558 0xb558 : { KEEP(*(.hook_b558)) }
	.text 0x1da00 : { KEEP(*(.text.low_entry)) KEEP(*(.text.low_fast_entry)) *(.text*) *(.rodata*) }
	.ram : { *(.data*) *(.bss*) *(COMMON) }
	/DISCARD/ : { *(.comment) *(.ARM.attributes) }
}

ASSERT(SIZEOF(.ram) == 0, "the patch must not use RAM variables")
ASSERT(SIZEOF(.hook_b41c) == 4, "hook b41c must be one tjl")
ASSERT(SIZEOF(.hook_b66e) == 4, "hook b66e must be one tjl")
ASSERT(SIZEOF(.hook_b558) == 4, "hook b558 must be one tjl")
