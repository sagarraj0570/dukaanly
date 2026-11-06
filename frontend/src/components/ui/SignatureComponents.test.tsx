import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { BillCard } from "./BillCard"
import { StatusStamp, orderStatusTone } from "./StatusStamp"
import { BazaarPattern } from "./BazaarPattern"

describe("Signature Components", () => {
  describe("BillCard", () => {
    it("renders every label and value, and footer is present", () => {
      const sampleRows = [
        { label: "Aashirvaad Atta", value: "₹450.00", sub: "10 kg pack" },
        { label: "Amul Milk", value: "₹144.00" },
        { label: "Tata Salt", value: "₹28.00" },
        { label: "Delivery Charge", value: "₹25.00", emphasis: true },
      ]

      render(
        <BillCard
          title="Chowdhury Kirana"
          note="Order #DKN-1234"
          rows={sampleRows}
          footer={{ label: "Total Amount", value: "₹647.00" }}
        />
      )

      expect(screen.getByText("Chowdhury Kirana")).toBeTruthy()
      expect(screen.getByText("Order #DKN-1234")).toBeTruthy()

      sampleRows.forEach((row) => {
        expect(screen.getByText(row.label)).toBeTruthy()
        expect(screen.getByText(row.value)).toBeTruthy()
      })
      expect(screen.getByText("10 kg pack")).toBeTruthy()

      expect(screen.getByText("Total Amount")).toBeTruthy()
      expect(screen.getByText("₹647.00")).toBeTruthy()
    })
  })

  describe("StatusStamp", () => {
    it("renders its text and tone colors properly", () => {
      render(<StatusStamp tone="success">Delivered</StatusStamp>)
      const el = screen.getByText("Delivered")
      expect(el).toBeTruthy()
      expect(el.className).toContain("rotate-[-2deg]")
    })

    it("orderStatusTone maps each specified status correctly plus unknown statuses", () => {
      // warning: pending, confirmed, preparing, offered
      expect(orderStatusTone("pending")).toBe("warning")
      expect(orderStatusTone("confirmed")).toBe("warning")
      expect(orderStatusTone("preparing")).toBe("warning")
      expect(orderStatusTone("offered")).toBe("warning")

      // neutral: ready_for_pickup, out_for_delivery, assigned, picked_up
      expect(orderStatusTone("ready_for_pickup")).toBe("neutral")
      expect(orderStatusTone("out_for_delivery")).toBe("neutral")
      expect(orderStatusTone("assigned")).toBe("neutral")
      expect(orderStatusTone("picked_up")).toBe("neutral")

      // success: delivered, accepted
      expect(orderStatusTone("delivered")).toBe("success")
      expect(orderStatusTone("accepted")).toBe("success")

      // danger: cancelled, rejected, expired
      expect(orderStatusTone("cancelled")).toBe("danger")
      expect(orderStatusTone("rejected")).toBe("danger")
      expect(orderStatusTone("expired")).toBe("danger")

      // unknown status fallback
      expect(orderStatusTone("unknown_custom_state")).toBe("neutral")
      expect(orderStatusTone("")).toBe("neutral")
    })
  })

  describe("BazaarPattern", () => {
    it("is aria-hidden and pointer-events-none in both variants", () => {
      const { container, rerender } = render(<BazaarPattern variant="strip" />)
      const stripEl = container.firstChild as HTMLElement
      expect(stripEl.getAttribute("aria-hidden")).toBe("true")
      expect(stripEl.className).toContain("pointer-events-none")
      expect(stripEl.className).toContain("h-[12px]")

      rerender(<BazaarPattern variant="fill" />)
      const fillEl = container.firstChild as HTMLElement
      expect(fillEl.getAttribute("aria-hidden")).toBe("true")
      expect(fillEl.className).toContain("absolute")
      expect(fillEl.className).toContain("inset-0")
    })
  })
})
