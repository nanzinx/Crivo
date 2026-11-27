"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AvaliacaoView } from "@/components/avaliacao/avaliacao-view";
import { useAuth } from "@/components/auth-context";
import { Card, Empty, Skeleton } from "@/components/ui/primitives";
import { api, type AvaliacaoCompleta } from "@/lib/api";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; av: AvaliacaoCompleta; leitura: boolean; aviso?: string }
  | { tipo: "vazio"; mensagem: string };

export default function AvaliarPage() {
  const params = useParams<{ id: string }>();
  const callId = Number(params.id);
  const { podeAvaliar, carregando } = useAuth();
  const { data: call, error } = useQuery({ queryKey: ["call", callId], queryFn: () => api.call(callId), enabled: Number.isFinite(callId) });
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    if (!call || carregando) return;
    let vivo = true;
    const somenteLer = async (aviso?: string) => {
      if (!call.avaliacao?.id) {
        setEstado({ tipo: "vazio", mensagem: aviso ?? "Esta ligação ainda não foi avaliada." });
        return;
      }
      const av = await api.avaliacao(call.avaliacao.id);
      if (vivo) setEstado({ tipo: "pronto", av, leitura: true, aviso });
    };
    const finalizada = call.status === "avaliada" || call.status === "nao_avaliavel";
    if (!podeAvaliar) somenteLer();
    else if (finalizada) api.avaliacao(call.avaliacao!.id).then((av) => vivo && setEstado({ tipo: "pronto", av, leitura: false }));
    else
      api
        .iniciarAvaliacao(callId)
        .then((av) => vivo && setEstado({ tipo: "pronto", av, leitura: false }))
        .catch((e: Error) => somenteLer(e.message));
    return () => {
      vivo = false;
    };
    // só na primeira carga da ligação
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call?.id, carregando, podeAvaliar]);

  return (
    <div className="space-y-4">
      <Link href="/monitoria" className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Fila de avaliação
      </Link>
      {error ? (
        <Card>
          <Empty title="Ligação não encontrada">{(error as Error).message}</Empty>
        </Card>
      ) : estado.tipo === "carregando" || !call ? (
        <div className="grid gap-4 lg:grid-cols-[5fr_7fr]">
          <Skeleton className="h-80" />
          <div className="space-y-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-64" />
          </div>
        </div>
      ) : estado.tipo === "vazio" ? (
        <Card>
          <Empty icon={<Lock className="h-5 w-5" />} title="Não dá para abrir a avaliação">
            {estado.mensagem}
          </Empty>
        </Card>
      ) : (
        <AvaliacaoView
          key={`${estado.av.id}-${estado.leitura}`}
          call={call}
          inicial={estado.av}
          somenteLeitura={estado.leitura}
          aviso={
            estado.aviso && (
              <p className="flex items-center gap-2 rounded-2xl bg-warn/15 p-3 text-sm">
                <Lock className="h-4 w-4 shrink-0" /> {estado.aviso}
              </p>
            )
          }
        />
      )}
    </div>
  );
}
