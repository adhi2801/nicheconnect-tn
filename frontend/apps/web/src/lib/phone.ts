// Indian mobile numbers. The API takes +91 followed by ten digits starting 6 to 9 (OtpRequestIn.phone).

/** Turn what a person typed into +91XXXXXXXXXX, or null when it is not a valid Indian mobile. */
export function normalizeIndianMobile(input: string): string | null {
  const cleaned = input.replace(/[\s\-().]/g, "");
  const match = /^(?:\+?91|0)?([6-9][0-9]{9})$/.exec(cleaned);
  return match ? `+91${match[1]}` : null;
}

/** "+919876543210" becomes "+91 98765 43210" for display. */
export function formatIndianMobile(e164: string): string {
  const m = /^\+91([0-9]{5})([0-9]{5})$/.exec(e164);
  return m ? `+91 ${m[1]} ${m[2]}` : e164;
}

/** The same number with the middle hidden, for a screen anyone could look over: "+91 ••••• ••210". */
export function maskIndianMobile(e164: string): string {
  const m = /^\+91[0-9]{7}([0-9]{3})$/.exec(e164);
  return m ? `+91 ••••• ••${m[1]}` : "your number";
}
