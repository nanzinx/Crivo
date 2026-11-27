"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldAlert, UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { api, type Usuario } from "@/lib/api";
import { cn, fmtAgo } from "@/lib/utils";

const PAPEIS: Record<string, { label: string; desc: string }> = {
  admin: { label: "Administrador", desc: "Tudo, inclusive gerenciar usuários" },
  monitora: { label: "Monitora de qualidade", desc: "Ouve as ligações e registra o resultado da avaliação" },
  supervisor: { label: "Supervisor", desc: "Consulta, confirma tabulações, importa, cuida dos alertas" },
  leitura: { label: "Só leitura", desc: "Só consulta" },
};

export default function UsuariosPage() {
  const { admin, usuario: eu } = useAuth();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["usuarios"], queryFn: api.usuarios, enabled: admin });
  const [novo, setNovo] = useState({ email: "", nome: "", papel: "supervisor", senha: "" });

  const criar = useMutation({
    mutationFn: () => api.criarUsuario(novo),
    onSuccess: (u) => {
      toast.success(`${u.nome} cadastrado`, { description: "Passe a senha provisória por um canal seguro e peça para trocar no primeiro acesso." });
      setNovo({ email: "", nome: "", papel: "supervisor", senha: "" });
      qc.invalidateQueries({ queryKey: ["usuarios"] });
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const editar = useMutation({
    mutationFn: ({ id, dados }: { id: number; dados: Parameters<typeof api.editarUsuario>[1] }) => api.editarUsuario(id, dados),
    onSuccess: () => {
      toast.success("Usuário atualizado");
      qc.invalidateQueries({ queryKey: ["usuarios"] });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  if (!admin) {
    return (
      <Card>
        <Empty icon={<ShieldAlert className="h-5 w-5" />} title="Só administradores gerenciam usuários" />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <header>
        <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-muted">
          <Users className="h-3.5 w-3.5 text-brand" /> Acesso ao painel
        </p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Usuários</h1>
      </header>

      <Card title="Cadastrar pessoa" subtitle="A senha é provisória: a pessoa troca em Minha conta">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            criar.mutate();
          }}
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1.3fr_180px_1fr_auto] lg:items-end"
        >
          {(
            [
              ["Nome", "nome", "text"],
              ["E-mail", "email", "email"],
            ] as const
          ).map(([label, k, type]) => (
            <label key={k} className="block">
              <span className="mb-1 block text-xs font-medium text-ink-2">{label}</span>
              <input
                type={type}
                required
                value={novo[k]}
                onChange={(e) => setNovo((x) => ({ ...x, [k]: e.target.value }))}
                className="h-9 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
              />
            </label>
          ))}
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-2">Perfil</span>
            <select
              value={novo.papel}
              onChange={(e) => setNovo((x) => ({ ...x, papel: e.target.value }))}
              className="h-9 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
            >
              {Object.entries(PAPEIS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-2">Senha provisória</span>
            <input
              type="text"
              required
              minLength={8}
              autoComplete="off"
              value={novo.senha}
              onChange={(e) => setNovo((x) => ({ ...x, senha: e.target.value }))}
              className="h-9 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
            />
          </label>
          <Button type="submit" variant="primary" loading={criar.isPending}>
            <UserPlus className="h-4 w-4" /> Cadastrar
          </Button>
        </form>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-ink-muted">
          {Object.values(PAPEIS).map((p) => (
            <li key={p.label}>
              <b className="font-medium text-ink-2">{p.label}:</b> {p.desc}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Equipe" subtitle={data ? `${data.length} usuário(s)` : undefined}>
        {isLoading || !data ? (
          <Skeleton className="h-40" />
        ) : (
          <ul className="divide-y divide-line">
            {data.map((u) => (
              <Linha key={u.id} u={u} eu={eu?.id === u.id} onEditar={(dados) => editar.mutate({ id: u.id, dados })} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Linha({ u, eu, onEditar }: { u: Usuario; eu: boolean; onEditar: (d: Parameters<typeof api.editarUsuario>[1]) => void }) {
  return (
    <li className={cn("grid gap-2 py-3 sm:grid-cols-[1fr_auto] sm:items-center", !u.ativo && "opacity-60")}>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {u.nome} {eu && <Pill tone="brand">você</Pill>} {!u.ativo && <Pill>inativo</Pill>}
        </p>
        <p className="truncate text-xs text-ink-muted">
          {u.email} · último acesso {u.ultimo_login_em ? fmtAgo(u.ultimo_login_em) : "nunca"}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={u.papel}
          onChange={(e) => onEditar({ papel: e.target.value })}
          aria-label={`Perfil de ${u.nome}`}
          className="h-8 rounded-lg border border-line bg-surface px-2 text-xs"
        >
          {Object.entries(PAPEIS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            const s = window.prompt(`Nova senha provisória para ${u.nome} (mínimo 8 caracteres):`);
            if (s) onEditar({ senha: s });
          }}
        >
          <KeyRound className="h-3.5 w-3.5" /> Redefinir senha
        </Button>
        {!eu && (
          <Button size="sm" variant={u.ativo ? "ghost" : "soft"} onClick={() => onEditar({ ativo: !u.ativo })}>
            {u.ativo ? "Desativar" : "Reativar"}
          </Button>
        )}
      </div>
    </li>
  );
}
