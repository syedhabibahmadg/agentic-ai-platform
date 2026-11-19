import {create} from "zustand";

export type User = {id: string; email: string; full_name: string; role: string;
  preferences: {theme?: "dark" | "light"; model?: string}};

export const useSession = create<{user: User | null; ready: boolean; setUser: (user: User | null) => void}>(
  set => ({user: null, ready: false, setUser: user => set({user, ready: true})})
);
