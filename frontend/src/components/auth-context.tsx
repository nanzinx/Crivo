"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api, type EstadoAuth, type Usuario } from "@/lib/api";

type Auth = {
  carregando: boolean;
  estado: EstadoAuth | undefined;
  usuario: Usuario | null;
  /** Pode alterar dados (revisar, confirmar tabulação, importar...). Falso para o perfil "só leitura". */
  podeEditar: boolean;
  admin: boolean;
  sair: () => Promise<void>;
};

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["auth"], queryFn: api.estadoAuth, staleTime: 60_000, retry: 0 });
  const usuario = data?.usuario ?? null;
  const semLogin = data ? !data.auth_ativo : false;
  const value: Auth = {
    carregando: isLoading,
    estado: data,
    usuario,
    podeEditar: semLogin || (!!usuario && usuario.papel !== "leitura"),
    admin: semLogin || usuario?.papel === "admin",
    sair: async () => {
      await api.logout().catch(() => undefined);
      qc.clear();
      window.location.href = "/login";
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth fora do AuthProvider");
  return v;
}
