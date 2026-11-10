// Names for the API data types, all derived from the types generated from openapi.yaml.
import type { components, operations } from './schema'

type Schemas = components['schemas']

export type AccountDeletion = Schemas['AccountDeletion']
export type Category = Schemas['Category']
export type Credentials = Schemas['Credentials']
export type DemoLoginResult = Schemas['DemoLoginResult']
export type Entry = Schemas['Entry']
export type EntryInput = Schemas['EntryInput']
export type EntryList = Schemas['EntryList']
export type ExportFile = Schemas['ExportFile']
export type Health = Schemas['Health']
export type LoginResult = Schemas['LoginResult']
export type Registration = Schemas['Registration']
export type Suggestion = Schemas['Suggestion']
export type SuggestionRequest = Schemas['SuggestionRequest']
export type Summary = Schemas['Summary']
export type SummaryFilter = Schemas['SummaryFilter']
export type SummaryList = Schemas['SummaryList']
export type SummaryUpdate = Schemas['SummaryUpdate']
export type TagList = Schemas['TagList']
export type User = Schemas['User']

/** The filters of `GET /entries`. */
export type EntryListQuery = NonNullable<operations['listEntries']['parameters']['query']>
