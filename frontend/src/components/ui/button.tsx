import {forwardRef, type ButtonHTMLAttributes} from "react";
import clsx from "clsx";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {variant?: "primary" | "secondary" | "ghost"};
export const Button = forwardRef<HTMLButtonElement, Props>(
  ({className, variant = "secondary", type = "button", ...props}, ref) =>
    <button ref={ref} type={type} className={clsx("button", variant, className)} {...props} />
);
