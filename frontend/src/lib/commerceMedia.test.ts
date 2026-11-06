import { describe, it, expect } from "vitest";
import { getProductImage, extractProductUnit, getShopCoverImage } from "./commerceMedia";

describe("commerceMedia getProductImage", () => {
  it("prioritizes product.imageUrl when explicitly provided", () => {
    const customUrl = "https://example.com/custom-packshot.png";
    expect(getProductImage("Any Product", "Any Category", customUrl)).toBe(customUrl);
  });

  it("resolves realistic images for medicines and pharmacy products", () => {
    const doloImg = getProductImage("Dolo 650 Paracetamol Tablets", "Medicines");
    expect(doloImg).toContain("images.unsplash.com");

    const vicksImg = getProductImage("Vicks VapoRub Balm", "Medicines");
    expect(vicksImg).toContain("images.unsplash.com");

    const bandAidImg = getProductImage("Band-Aid Medicated Strips", "Medicines");
    expect(bandAidImg).toContain("images.unsplash.com");

    const orsImg = getProductImage("Electral ORS Powder", "Medicines");
    expect(orsImg).toContain("images.unsplash.com");
  });

  it("resolves realistic images for groceries and household brands", () => {
    const attaImg = getProductImage("Aashirvaad Superior MP Shudh Chakki Atta 5kg", "Groceries");
    expect(attaImg).toContain("aashirvaad-atta-whole-wheat");

    const saltImg = getProductImage("Tata Salt Vacuum Evaporated Iodised Salt 1kg", "Groceries");
    expect(saltImg).toContain("tata-salt-iodized");

    const surfImg = getProductImage("Surf Excel Easy Wash Detergent Powder", "Household Essentials");
    expect(surfImg).toContain("images.unsplash.com");
  });

  it("resolves bakery and snack specialties accurately", () => {
    const truffleImg = getProductImage("Dutch Dark Chocolate Truffle Cake", "Bakery");
    expect(truffleImg).toContain("images.unsplash.com");

    const pavImg = getProductImage("The Bakeway Soft Pav Buns", "Bakery");
    expect(pavImg).toContain("images.unsplash.com");

    const bhujiaImg = getProductImage("Haldiram Nagpur Bhujia Sev", "Snacks");
    expect(bhujiaImg).toContain("images.unsplash.com");
  });

  it("falls back to category defaults when specific item keywords do not match", () => {
    const genericMedicine = getProductImage("Unlisted Tablet", "Medicines");
    expect(genericMedicine).toContain("photo-1584308666744");

    const genericDairy = getProductImage("Unlisted Dairy Product", "Dairy");
    expect(genericDairy).toContain("images.unsplash.com");
  });
});

describe("commerceMedia extractProductUnit", () => {
  it("extracts weight and volume units accurately", () => {
    expect(extractProductUnit("Aashirvaad Chakki Atta 5kg")).toBe("5kg");
    expect(extractProductUnit("Sudha Gold Milk 500ml")).toBe("500ml");
    expect(extractProductUnit("Dettol Soap 125g (Pack of 3)")).toBe("125g");
    expect(extractProductUnit("Fortune Sunflower Oil 1L")).toBe("1L");
  });

  it("returns null when no unit is present", () => {
    expect(extractProductUnit("Fresh Red Apples")).toBeNull();
  });
});

describe("commerceMedia getShopCoverImage", () => {
  it("returns appropriate storefronts by keyword match", () => {
    expect(getShopCoverImage("Patna Super Kirana")).toBeTruthy();
    expect(getShopCoverImage("Pataliputra Bakery")).toBeTruthy();
  });
});
