// Tipurile API-ului, generate din backend (npm run api-types → schema.d.ts).
import type { components } from "./schema";

type S = components["schemas"];

export type Me = S["MeOut"];
export type AccessToken = S["AccessTokenOut"];
export type ClientListOut = S["ClientListOut"];
export type ClientListItem = S["ClientListItem"];
export type ClientOut = S["ClientOut"];
export type ClientSaveOut = S["ClientSaveOut"];
export type ClientCreate = S["ClientCreate"];
export type ClientUpdate = S["ClientUpdate"];
export type AssignmentOut = S["AssignmentOut"];
export type ClientReportTypeOut = S["ClientReportTypeOut"];
export type RecalculateDiff = S["RecalculateDiff"];
export type GridOut = S["GridOut"];
export type EntryOut = S["EntryOut"];
export type GenerationOut = S["GenerationOut"];
export type StatusSetOut = S["StatusSetOut"];
export type ReportTypeOut = S["ReportTypeOut"];
export type ReportTypeDetailOut = S["ReportTypeDetailOut"];
export type CategoryOut = S["CategoryOut"];
export type UserOut = S["UserOut"];
export type UserRole = Me["role"];
