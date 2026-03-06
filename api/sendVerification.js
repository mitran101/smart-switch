import nodemailer from "nodemailer";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  try {
    const { email } = req.body;

    if (!email) {
      res.status(400).json({ error: "Email is required" });
      return;
    }

    // Generate simple token
    const token = Array(32)
      .fill(0)
      .map(() => "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".charAt(Math.floor(Math.random() * 62)))
      .join("");

    const transporter = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT || 587),
      secure: false,
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS,
      },
    });

    const link = `https://switchpilot.com/verify?token=${token}&email=${encodeURIComponent(email)}`;

    await transporter.sendMail({
      from: `SwitchPilot Team <${process.env.SMTP_USER}>`,
      to: email,
      subject: "Verify your email — SwitchPilot",
      html: `
        <p>Hello,</p>
        <p>Please click the link below to verify your email:</p>
        <p><a href="${link}">${link}</a></p>
        <p>If you didn’t request this, ignore this email.</p>
      `,
    });

    res.status(200).json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ success: false, error: "Failed to send email" });
  }
}
