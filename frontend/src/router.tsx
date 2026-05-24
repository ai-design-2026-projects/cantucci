import { createBrowserRouter } from 'react-router-dom'
import App from './App'
import { LoginPage } from './features/Auth/LoginPage'
import { RegisterPage } from './features/Auth/RegisterPage'

/**
 * Application router. All main-app paths share the App layout shell.
 * Auth pages are independent full-page routes.
 */
export const router = createBrowserRouter([
	{
		path: '/login',
		element: <LoginPage />,
	},
	{
		path: '/register',
		element: <RegisterPage />,
	},
	{
		path: '/',
		element: <App />,
	},
	{
		path: '/conversation/:conversationId',
		element: <App />,
	},
])
