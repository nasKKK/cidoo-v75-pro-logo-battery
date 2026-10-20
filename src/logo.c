// Logo LED shows the battery charge. Patch for the factory firmware of Cidoo V75 Pro, V0101.
// Active only in logo mode 3 (static colour) with colour 7 (white in the factory Fn+PgDn cycle);
// otherwise the factory code runs unchanged. The addresses are those of firmware V0101.
//
//   battery 100..20 %  hue from green to red through yellow and orange, steady
//   battery  < 20 %    red flash every 2.1 s: fast rise, slow fall, dark pause
//   cable, charging    green cascade: the bar fills from the bottom (LED 2, 1, 0), holds, all fall fast
//   cable, charged     green flash of the same shape as the red one, every 4.2 s
//
// No division anywhere: libgcc is not linked, so periods are powers of two of the system timer.

typedef unsigned char u8;
typedef unsigned int u32;

#define REG8(a)  (*(volatile u8 *)(a))
#define REG32(a) (*(volatile u32 *)(a))

#define PIN_PD      REG8(0x800598)   // bit 7: cable power in, bit 6: charging
#define SYS_TICK    REG32(0x800740)  // 16 MHz system timer
#define BATT_PCT    REG8(0x8459a0)   // battery, percent
#define LOGO_MODE   REG8(0x8459e6)   // logo mode 0..4 (Fn+PgUp)
#define LOGO_COLOR  REG8(0x8459ea)   // logo colour 0..8 (Fn+PgDn)
#define LOGO_TICK   REG8(0x8473eb)   // logo frame counter, counted up by the timer interrupt
#define LOGO_R      REG8(0x8473e5)   // logo colour as last drawn
#define LOGO_G      REG8(0x8472e6)
#define LOGO_B      REG8(0x8472d8)
#define LED_FLAGS2  REG8(0x847232)   // bit 4: LED output off
#define LED_FLAGS3  REG8(0x847233)   // bit 2: Fn blink, on phase

#define MODE_STATIC    3
#define COLOR_BATTERY  7
#define LOGO_FRAME     11            // the factory static mode redraws when LOGO_TICK > 11

#define RGB_GREEN   0x00ff00
#define RGB_RED     0xff0000

#define KEY_FN      0x55

// Flash: SYS_TICK >> shift counts 1024 steps per period (shift 15: 2.1 s, shift 16: 4.2 s).
#define SHIFT_RED      15
#define SHIFT_CHARGED  16
#define FLASH_RISE     128           // 1/8 of the period
#define FLASH_FALL     768           // 6/8 of the period, then dark for 1/8

// Cascade: 1024 steps of 4.1 ms (4.2 s).
#define SHIFT_CASCADE  16
#define CASCADE_STEP   288           // 1.18 s between the LEDs: the next starts when the one before is at 97 %
                                     // rise: 320 steps (1.31 s) for the first two, 256 (1.05 s) for the last
#define CASCADE_TOP    928           // all lit from 832; held 0.39 s
#define CASCADE_FALL   64            // 0.26 s, then dark until the period ends

extern void fw_logo_static(void);                     // 0xb348
extern void fw_logo_led(int n, int r, int g, int b);  // 0x9030
extern void fw_key_led(int key, int r, int g, int b); // 0x8fbc

// Smooth step 0..256 -> 0..256 (3u^2 - 2u^3).
static u32 ease(u32 u)
{
	if (u >= 256)
		return 256;
	return (u * u * (768 - 2 * u)) >> 16;
}

static u32 flash(u32 shift)
{
	u32 x = (SYS_TICK >> shift) & 1023;

	if (x < FLASH_RISE)
		return ease(x * 2);
	if (x < FLASH_RISE + FLASH_FALL)
		return 256 - ease(((x - FLASH_RISE) * 85) >> 8); // (x - rise) / 3
	return 0;
}

static u32 cascade(int n)
{
	u32 x = (SYS_TICK >> SHIFT_CASCADE) & 1023;
	int k = 2 - n; // order from the bottom: LED 2 is the bottom one
	u32 start = CASCADE_STEP * k;

	if (x >= CASCADE_TOP)
		return x < CASCADE_TOP + CASCADE_FALL ? 256 - ease((x - CASCADE_TOP) * 4) : 0;
	if (x < start)
		return 0;
	if (k == 2)
		return ease(x - start);                // the last one: 256 steps
	return ease(((x - start) * 205) >> 8);         // the first two: 320 steps
}

// Colour for 100..20 %: green -> yellow -> red at full brightness.
static u32 charge_rgb(u32 pct)
{
	u32 x;

	if (pct > 100)
		pct = 100;
	x = pct - 20; // 0..80
	if (x <= 40)
		return 0xff0000 | (((x * 51) >> 3) << 8);
	return (((80 - x) * 51) >> 3) << 16 | 0x00ff00;
}

// One LED at brightness v (0..256), with gamma 2 so that fades look even to the eye.
static void led_set(int n, u32 rgb, u32 v)
{
	u32 k = (v * v) >> 8;
	u8 r = (((rgb >> 16) & 0xff) * k) >> 8;
	u8 g = (((rgb >> 8) & 0xff) * k) >> 8;
	u8 b = ((rgb & 0xff) * k) >> 8;

	LOGO_R = r;
	LOGO_G = g;
	LOGO_B = b;
	fw_logo_led(n, r, g, b);
}

static void logo_all(u32 rgb, u32 v)
{
	int n;

	for (n = 0; n < 3; n++)
		led_set(n, rgb, v);
}

static int battery_logo_on(void)
{
	return LOGO_MODE == MODE_STATIC && LOGO_COLOR == COLOR_BATTERY;
}

// Called instead of fw_logo_static in logo mode 3 (hook at 0xb41c).
void logo_normal(void)
{
	u8 pin;
	int n;

	if (LOGO_COLOR != COLOR_BATTERY) {
		fw_logo_static();
		return;
	}
	if (LOGO_TICK <= LOGO_FRAME)
		return;
	LOGO_TICK = 0;

	pin = PIN_PD;
	if (pin & 0x80) {
		if (pin & 0x40) {
			for (n = 0; n < 3; n++)
				led_set(n, RGB_GREEN, cascade(n));
		} else {
			logo_all(RGB_GREEN, flash(SHIFT_CHARGED));
		}
		return;
	}
	if (BATT_PCT < 20)
		logo_all(RGB_RED, flash(SHIFT_RED));
	else
		logo_all(charge_rgb(BATT_PCT), 256);
}

// Low battery (<= 19 % on battery): red flash; LED output switched on while it is lit.
static void low_draw(void)
{
	u32 v = flash(SHIFT_RED);

	if (v)
		LED_FLAGS2 &= ~0x10;
	logo_all(RGB_RED, v);
}

// Low battery branch, every 40 counts, after the factory code cleared the LED buffers
// (hook at 0xb66e). Does what the factory code did, then the logo.
void logo_low(void)
{
	LED_FLAGS2 |= 0x10;
	if (LED_FLAGS3 & 4) {
		LED_FLAGS2 &= ~0x10;
		fw_key_led(KEY_FN, 0xff, 0, 0);
	}
	if (battery_logo_on())
		low_draw();
}

// Low battery branch between those refreshes (hook at 0xb558): the logo at the normal frame rate,
// so that the flash is as smooth as in the other states.
void logo_low_fast(void)
{
	if (!battery_logo_on() || LOGO_TICK <= LOGO_FRAME)
		return;
	LOGO_TICK = 0;
	low_draw();
}
