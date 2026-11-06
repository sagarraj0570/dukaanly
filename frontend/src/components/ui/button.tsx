import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[12px] border border-transparent bg-clip-padding text-sm font-semibold whitespace-nowrap transition-all outline-none select-none active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-leaf text-leaf-ink hover:bg-leaf-hover",
        primary: "bg-leaf text-leaf-ink hover:bg-leaf-hover",
        outline:
          "border border-border-strong text-ink hover:bg-sand aria-expanded:bg-sand",
        secondary:
          "bg-sand text-ink border border-border hover:bg-[color-mix(in_srgb,var(--sand),var(--ink)_5%)] aria-expanded:bg-sand",
        ghost:
          "text-ink hover:bg-sand aria-expanded:bg-sand",
        accent:
          "bg-turmeric-tint text-ink border border-turmeric hover:bg-[#EBD6A2]",
        destructive:
          "bg-brick-tint text-brick-ink border border-brick hover:bg-brick-tint/80",
        link: "text-leaf underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-[44px] h-11 gap-2 px-4 py-2",
        xs: "min-h-[28px] h-7 gap-1 rounded-[8px] px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "min-h-[36px] h-9 gap-1.5 rounded-[10px] px-3 text-xs [&_svg:not([class*='size-'])]:size-3.5",
        lg: "min-h-[48px] h-12 gap-2 px-5 text-base",
        icon: "size-11 min-h-[44px] p-0",
        "icon-xs": "size-7 min-h-[28px] rounded-[8px] p-0 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-9 min-h-[36px] rounded-[10px] p-0 [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-12 min-h-[48px] p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
