export interface PreviewProduct {
  id: string
  name: string
  weight: string
  price: number
  category: string
  imageUrl: string
  shopName: string
}

export const AUTH_PREVIEW_PRODUCTS: PreviewProduct[] = [
  {
    id: 'prev-1',
    name: 'Sudha Gold Full Cream Milk',
    weight: '500 ml',
    price: 28,
    category: 'Dairy',
    imageUrl: 'https://images.unsplash.com/photo-1563636619-e9143da7973b?auto=format&fit=crop&w=160&q=80',
    shopName: 'Kankarbagh Daily',
  },
  {
    id: 'prev-2',
    name: "Haldiram's Bhujia Sev",
    weight: '200 g',
    price: 45,
    category: 'Snacks',
    imageUrl: 'https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=160&q=80',
    shopName: 'Sharma Kirana',
  },
  {
    id: 'prev-3',
    name: 'Tata Salt Vacuum Evaporated',
    weight: '1 kg',
    price: 26,
    category: 'Groceries',
    imageUrl: 'https://images.unsplash.com/photo-1581441363689-1f3c3c414635?auto=format&fit=crop&w=160&q=80',
    shopName: 'Patna Kirana Bazar',
  },
]
