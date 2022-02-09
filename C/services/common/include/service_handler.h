#ifndef _SERVICE_HANDLER_H
#define _SERVICE_HANDLER_H
/*
 * Fledge storage service.
 *
 * Copyright (c) 2017 OSisoft, LLC
 *
 * Released under the Apache 2.0 Licence
 *
 * Author: Mark Riddoch, Massimiliano Pinto
 */
#include <config_category.h>
#include <string>
#include <management_client.h>

/**
 * ServiceHandler abstract class - the interface that services using the
 * management API must provide.
 */
class ServiceHandler
{
	public:
		virtual void	shutdown() = 0;
		virtual void	configChange(const std::string& category, const std::string& config) = 0;
};

/**
 * ServiceAuthHandler adds security to the base class ServiceHandler
 */
class ServiceAuthHandler : public ServiceHandler
{
	public:
		std::string&		getName() { return m_name; };
		bool			createSecurityCategories(ManagementClient* mgtClient);
		bool			updateSecurityCategory(const std::string& newCategory);
		void			setInitialAuthenticatedCaller();
		void			setAuthenticatedCaller(bool enabled);
		bool			getAuthenticatedCaller();
		void			AuthenticationMiddlewarePUT(std::shared_ptr<HttpServer::Response> response,
								std::shared_ptr<HttpServer::Request> request,
								std::function<void(
									std::shared_ptr<HttpServer::Response>,
									std::shared_ptr<HttpServer::Request>)> funcPUT);
		void			AuthenticationMiddlewarePOST(std::shared_ptr<HttpServer::Response> response,
								std::shared_ptr<HttpServer::Request> request,
								std::function<void(
									std::shared_ptr<HttpServer::Response>,
									std::shared_ptr<HttpServer::Request>)> funcPOST);
 		// Send a good HTTP response to the caller
		void			respond(std::shared_ptr<HttpServer::Response> response,
								const std::string& payload)
					{
						*response << "HTTP/1.1 200 OK\r\n"
							<< "Content-Length: " << payload.length() << "\r\n"
							<<  "Content-type: application/json\r\n\r\n"
							<< payload;
					};
 		// Send an error messagei HTTP response to the caller with given HTTP code
		void			respond(std::shared_ptr<HttpServer::Response> response,
								SimpleWeb::StatusCode code,
								const std::string& payload)
					{
						*response << "HTTP/1.1 " << status_code(code) << "\r\n"
							<< "Content-Length: " << payload.length() << "\r\n"
							<<  "Content-type: application/json\r\n\r\n"
							<< payload;
					};
		static ManagementClient *
					getMgmtClient() { return m_mgtClient; };

	private:
		bool			verifyURL(const std::string& path, std::map<std::string, std::string> claims);
		bool			verifyService(std::string& sName, std::string &sType);

	protected:
		std::string		m_name;
		// Management client pointer
		static ManagementClient
					*m_mgtClient;

	private:
		// Security configuration change mutex
		std::mutex		m_mtx_config;
		// Authentication is enabled for API endpoints
		bool			m_authentication_enabled;
		// Security configuration
		ConfigCategory		m_security;
};

#endif
