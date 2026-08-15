import { DownloadSimple, X } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

interface CheckInCardProps {
  imageUrl: string;
  caption: string;
  cafeName?: string;
  tableNumber: string;
  onClose: () => void;
}

const CARD_WIDTH = 1080;
const CARD_HEIGHT = 1350;

function formatDate(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}.${m}.${d}`;
}

export function CheckInCard({
  imageUrl,
  caption,
  cafeName = "DD 咖啡馆",
  tableNumber,
  onClose,
}: CheckInCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [dataUrl, setDataUrl] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = imageUrl;
    img.onload = () => {
      canvas.width = CARD_WIDTH;
      canvas.height = CARD_HEIGHT;

      // 1. Draw background fill
      ctx.fillStyle = "#1a1a2e";
      ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

      // 2. Draw photo — scaled to cover the card, vertically centered
      const scale = Math.max(CARD_WIDTH / img.width, CARD_HEIGHT / img.height);
      const sw = CARD_WIDTH / scale;
      const sh = CARD_HEIGHT / scale;
      const sx = (img.width - sw) / 2;
      const sy = (img.height - sh) / 2;
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, CARD_WIDTH, CARD_HEIGHT);

      // 3. Bottom gradient overlay (brand green)
      const gradient = ctx.createLinearGradient(0, CARD_HEIGHT * 0.55, 0, CARD_HEIGHT);
      gradient.addColorStop(0, "rgba(35, 95, 70, 0)");
      gradient.addColorStop(0.5, "rgba(35, 95, 70, 0.25)");
      gradient.addColorStop(1, "rgba(20, 60, 45, 0.75)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

      // 4. Vignette (radial gradient)
      const vignette = ctx.createRadialGradient(
        CARD_WIDTH / 2,
        CARD_HEIGHT / 2,
        CARD_WIDTH * 0.55,
        CARD_WIDTH / 2,
        CARD_HEIGHT / 2,
        CARD_WIDTH * 0.85,
      );
      vignette.addColorStop(0, "rgba(0,0,0,0)");
      vignette.addColorStop(1, "rgba(0,0,0,0.3)");
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

      // 5. Cafe name — top left
      ctx.font = "bold 52px 'PingFang SC', 'Noto Sans SC', 'Heiti SC', sans-serif";
      ctx.fillStyle = "#ffffff";
      ctx.shadowColor = "rgba(0,0,0,0.5)";
      ctx.shadowBlur = 12;
      ctx.fillText(cafeName, 56, 96);
      ctx.shadowBlur = 0;

      // 6. Date — top right
      ctx.font = "32px 'PingFang SC', 'Noto Sans SC', 'Heiti SC', sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      const dateStr = formatDate();
      const dateWidth = ctx.measureText(dateStr).width;
      ctx.fillText(dateStr, CARD_WIDTH - dateWidth - 56, 88);

      // 7. Caption — bottom area
      ctx.font = "bold 44px 'PingFang SC', 'Noto Sans SC', 'Heiti SC', sans-serif";
      ctx.fillStyle = "#ffffff";
      ctx.shadowColor = "rgba(0,0,0,0.4)";
      ctx.shadowBlur = 8;
      ctx.fillText(caption, 56, CARD_HEIGHT - 200);
      ctx.shadowBlur = 0;

      // 8. Table badge — bottom right
      const badgeText = `${tableNumber} 桌`;
      ctx.font = "28px 'PingFang SC', 'Noto Sans SC', 'Heiti SC', sans-serif";
      const badgeW = ctx.measureText(badgeText).width + 32;
      const badgeH = 44;
      const badgeX = CARD_WIDTH - badgeW - 56;
      const badgeY = CARD_HEIGHT - 100;
      ctx.fillStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath();
      ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 22);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.fillText(badgeText, badgeX + 16, badgeY + 32);

      // 9. Brand watermark — bottom left
      ctx.font = "24px 'PingFang SC', 'Noto Sans SC', 'Heiti SC', sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.5)";
      ctx.fillText("DD Cafe · 打卡", 56, CARD_HEIGHT - 100);

      setDataUrl(canvas.toDataURL("image/jpeg", 0.92));
      setLoading(false);
    };
    img.onerror = () => {
      setLoading(false);
    };
  }, [imageUrl, caption, cafeName, tableNumber]);

  const handleDownload = () => {
    if (!dataUrl) return;
    const link = document.createElement("a");
    link.download = `DD-Cafe-${formatDate()}.jpg`;
    link.href = dataUrl;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="checkin-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="checkin-modal"
        role="dialog"
        aria-modal="true"
        aria-label="打卡卡片预览"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="checkin-header">
          <h3>你的打卡卡片</h3>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}>
            <X size={20} />
          </button>
        </header>
        <div className="checkin-preview">
          {loading && <div className="checkin-loading">生成中…</div>}
          <canvas
            ref={canvasRef}
            style={{ display: loading ? "none" : "block", width: "100%", borderRadius: "16px" }}
          />
          {dataUrl && (
            <img
              src={dataUrl}
              alt="打卡卡片预览"
              style={{ display: "none" }}
            />
          )}
        </div>
        <div className="checkin-actions">
          <button
            className="checkin-download-btn"
            type="button"
            disabled={!dataUrl}
            onClick={handleDownload}
          >
            <DownloadSimple size={20} weight="bold" />
            保存到相册
          </button>
        </div>
      </div>
    </div>
  );
}
