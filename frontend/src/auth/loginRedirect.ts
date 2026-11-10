// Connects the API client's "not authenticated" redirect (#25) to the router, so a 401 on
// any page opens /login inside the app and remembers the page, like the route guard does.
import type { DataRouter } from 'react-router'
import { setLoginRedirect } from '../api/index.ts'
import { LOGIN_PATH, rememberWantedPage } from './wantedPage.ts'

type RouterLike = Pick<DataRouter, 'state' | 'navigate'>

export function connectLoginRedirect(router: RouterLike): void {
  setLoginRedirect(() => {
    const { location } = router.state
    if (location.pathname === LOGIN_PATH) {
      return
    }
    void router.navigate(LOGIN_PATH, { replace: true, state: rememberWantedPage(location) })
  })
}
